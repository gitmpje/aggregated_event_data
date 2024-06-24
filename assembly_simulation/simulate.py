import argparse
import sys

from collections import defaultdict
from json import load
from pathlib import Path
from random import seed
from simpy import Environment, Store

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from assembly_simulation.controller import Controller
from assembly_simulation.logging import SimulationEventLogging
from assembly_simulation.production_entities import ProductionLot
from assembly_simulation.production_resources import PackingResource, ProductionResource

def main():
    parser = argparse.ArgumentParser(
        prog="assembly_simulation",
        description="",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("config_file", help="Path to simulation configuration file.")
    parser.add_argument("-s", "--random_seed", help="Maximum simulation time.", default=0)
    parser.add_argument("-r", "--runtime", help="Maximum simulation time.", default=100)

    args = parser.parse_args()

    with open(args.config_file) as f:
        config = load(f)

    seed(args.random_seed)

    production_lots = [
        ProductionLot(
            r["id"],
            r["steps"],
            r["merge"],
            r["split"],
            [f"{r['id']}_Device{d}" for d in range(r["n_devices"])]
        )
        for r in config["production_lots"]
    ]

    env = Environment()
    production_lots_store = Store(env)
    production_lots_store.items = production_lots

    production_resources = [
        ProductionResource(
            env,
            r["id"],
            r["step"],
            r["mean_move"],
            r["mean_duration"],
            r["mean_breakdown"],
            r["mean_repair"],
            production_lots_store
        )
        for r in config["production_resources"]
    ]

    production_resources_dict = defaultdict(list)
    for resource in production_resources:
        production_resources_dict[resource.capability].append(resource)


    packing_store = Store(env)
    packing_resource = PackingResource(env, config["packing_unit_size"], packing_store)

    controller = Controller(
        env,
        production_resources_dict,
        production_lots_store,
        packing_store
    )

    simulation_event_logging = SimulationEventLogging(env, Path(args.config_file).stem)
    env.run(args.runtime)
    print(packing_resource.packing_units)

    simulation_event_logging.write_json_event_data()

if __name__=="__main__":
    main()