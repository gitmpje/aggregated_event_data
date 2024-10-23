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
from assembly_simulation.production_entities import (
    Device,
    MaterialLot,
    MergeConfiguration,
    ProductionLot,
    SplitConfiguration,
)
from assembly_simulation.production_resources import PackingResource, ProductionResource


def main(
    config_file: str,
    runtime: int,
    random_seed: int = None,
    output_event_log_file: str = None,
):
    with open(config_file) as f:
        config = load(f)

    if random_seed:
        seed(random_seed)

    # Instantiate environment and logging
    env = Environment()
    logging_id = f"{Path(config_file).stem}{'_'+random_seed if random_seed else ''}"
    simulation_event_logging = SimulationEventLogging(
        env, identifier=logging_id, event_log_file=output_event_log_file
    )
    env.logging = simulation_event_logging

    production_lots = [
        ProductionLot(
            env=env,
            identifier=r["id"],
            required_steps=r["steps"],
            required_material=r.get("required_material", dict()),
            merge_configs=[
                MergeConfiguration(**config) for config in r.get("merge", [])
            ],
            split_configs=[
                SplitConfiguration(**config) for config in r.get("split", [])
            ],
            devices=[
                Device(identifier=f"{r['id']}_Device{d}") for d in range(r["n_devices"])
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
                    material_type=m,
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
            process_yield=r.get("process_yield", 1),
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

    env.run(runtime)
    print(packing_resource.packing_units)

    simulation_event_logging.write_json_event_data()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="assembly_simulation",
        description="",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("config_file", help="Path to simulation configuration file.")
    parser.add_argument(
        "-s",
        "--random_seed",
        help="Seed to be used for the simulation.",
        default=None,
    )
    parser.add_argument(
        "-o",
        "--output_event_log_file",
        help="Name/path of the out file with the event log.",
        default=None,
    )
    parser.add_argument("-r", "--runtime", help="Maximum simulation time.", default=100)

    args = parser.parse_args()

    main(
        config_file=args.config_file,
        runtime=args.runtime,
        random_seed=args.random_seed,
        output_event_log_file=args.output_event_log_file,
    )
