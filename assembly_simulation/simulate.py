import argparse
import sys

from collections import defaultdict
from json import load
from math import ceil
from pathlib import Path
from random import seed
from simpy import Environment, FilterStore, Store

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from assembly_simulation.controller import Controller
from assembly_simulation.logging import SimulationEventLogging
from assembly_simulation.production_entities import MaterialLot, ProductionLot
from assembly_simulation.production_resources import PackingResource, ProductionResource


def main():
    parser = argparse.ArgumentParser(
        prog="assembly_simulation",
        description="",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("config_file", help="Path to simulation configuration file.")
    parser.add_argument(
        "-s", "--random_seed", help="Maximum simulation time.", default=None
    )
    parser.add_argument("-r", "--runtime", help="Maximum simulation time.", default=100)

    args = parser.parse_args()

    with open(args.config_file) as f:
        config = load(f)

    if args.random_seed:
        seed(args.random_seed)

    # Instantiate environment and logging
    env = Environment()
    simulation_event_logging = SimulationEventLogging(
        env,
        f"{Path(args.config_file).stem}{'_'+args.random_seed if args.random_seed else ''}",
    )
    env.logging = simulation_event_logging

    production_lots = [
        ProductionLot(
            env=env,
            identifier=r["id"],
            required_steps=r["steps"],
            required_material=r.get("required_material", dict()),
            merge_configuration=r["merge"],
            split_configuration=r["split"],
            devices=[
                {"identifier": f"{r['id']}_Device{d}", "materials": []}
                for d in range(r["n_devices"])
            ],
        )
        for r in config["production_lots"]
    ]

    # Generate material lots based on required materials
    required_materials = defaultdict(int)
    for r in config["production_lots"]:
        for m in r.get("required_material", {}).values():
            required_materials[m] += r["n_devices"]  # one material unit per device

    material_lots = []
    for m, q in required_materials.items():
        material_lots.extend(
            [
                MaterialLot(
                    env=env,
                    identifier=f"{m}_{i}",
                    type=m,
                    quantity=config["material_lot_size"],
                )
                for i in range(ceil(q / config["material_lot_size"]))
            ]
        )

    production_lots_store = Store(env)
    production_lots_store.items = production_lots
    material_lots_store = FilterStore(env)
    material_lots_store.items = material_lots

    production_resources = [
        ProductionResource(
            env=env,
            identifier=r["id"],
            capability=r["step"],
            mean_move=r["mean_move"],
            mean_duration=r["mean_duration"],
            mean_breakdown=r["mean_breakdown"],
            mean_repair=r["mean_repair"],
            lot_store=production_lots_store,
            material_lot_store=material_lots_store,
        )
        for r in config["production_resources"]
    ]

    production_resources_dict = defaultdict(list)
    for resource in production_resources:
        production_resources_dict[resource.capability].append(resource)

    packing_store = Store(env)
    packing_resource = PackingResource(env, config["packing_unit_size"], packing_store)

    controller = Controller(
        env, production_resources_dict, production_lots_store, packing_store
    )

    env.run(args.runtime)
    print(packing_resource.packing_units)

    simulation_event_logging.write_json_event_data()


if __name__ == "__main__":
    main()
