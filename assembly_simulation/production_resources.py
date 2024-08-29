from collections import defaultdict
from random import expovariate, shuffle
from simpy import Environment, Interrupt, PriorityStore, Store

from assembly_simulation.production_entities import ProductionLot


class ProductionResource:
    def __init__(
        self,
        env: Environment,
        identifier: str,
        capability: str,
        mean_move: float,
        mean_duration: float,
        mean_breakdown: float,
        mean_repair: float,
        lot_store: Store,
    ) -> None:
        self.env = env

        self.identifier = identifier
        self.capability = capability
        self.mean_move = mean_move
        self.mean_duration = mean_duration
        self.mean_breakdown = mean_breakdown
        self.mean_repair = mean_repair
        self.lot_store = lot_store

        self.state = "Idle"
        self.queue = PriorityStore(env)
        self.running_process = env.process(self.running())

    def running(self):
        while True:
            if self.state == "Idle":
                # Get next production lot in queue to start working on
                priority_item = yield self.queue.get()
                lot = priority_item.item
                done_in = expovariate(1 / self.mean_duration)

                # Wait for the lot to arrive at the resource
                yield self.env.timeout(
                    expovariate(self.mean_move),
                    value={
                        "eventType": "Object",
                        "bizStep": "arriving",
                        "entity": lot.identifier,
                        "location": self.identifier,
                        "quantity": {
                            "amount": len(lot.devices),
                            "class": lot.identifier,
                        },
                        "_devices": lot.devices.copy(),
                    },
                )
                print(
                    f"{self.identifier} [{self.env.now}] - Start processing {lot.identifier}"
                )
            else:
                # Resume processing a production lot
                print(
                    f"{self.identifier} [{self.env.now}] - Resume processing {lot.identifier}"
                )
                done_in = remaining_time

            start = self.env.now
            breakdown = self.env.process(self.breakdown())
            processing = self.env.timeout(
                done_in,
                value={
                    "eventType": "Object",
                    "bizStep": "departing",
                    "entity": lot.identifier,
                    "location": self.identifier,
                    "quantity": {
                        "amount": len(lot.devices),
                        "class": lot.identifier,
                    },
                    "_devices": lot.devices.copy(),
                },
            )
            self.state = "Processing"

            yield processing | breakdown
            if not breakdown.triggered:
                breakdown.interrupt()  # stop breakdown process
                print(
                    f"{self.identifier} [{self.env.now}] - Finished processing {lot.identifier}"
                )

                self.state = "Idle"
                lot.executed_steps.append(self.capability)
                self.lot_store.put(lot)
            else:
                # Breakdown of the resource
                processing._value = None
                remaining_time = done_in - (
                    self.env.now - start
                )  # remaining process time

                self.state = "Broken"
                yield self.env.timeout(expovariate(1 / self.mean_repair))
                print(f"{self.identifier} [{self.env.now}] - Repaired")

    def breakdown(self):
        try:
            yield self.env.timeout(expovariate(1 / self.mean_breakdown))
            print(f"{self.identifier} [{self.env.now}] - Breakdown")
        except Interrupt:
            pass


class PackingResource:
    def __init__(self, env: Environment, packing_size: int, packing_store: Store):
        self.env = env
        self.identifier = "PackingResource"
        self.packing_size = packing_size
        self.packing_store = packing_store

        self.packing_units = {}
        self.remainder = []

        self.resource_running = env.process(self.running())

    def running(self):
        while True:
            # Can be extended to get lots based on product type
            lot_to_pack = yield self.packing_store.get()
            shuffle(lot_to_pack.devices)

            # Create list with lot-device pairs
            self.remainder.extend(
                zip([lot_to_pack] * len(lot_to_pack.devices), lot_to_pack.devices)
            )

            # Create packing units
            devices_list = list(zip(*(iter(self.remainder),) * self.packing_size))
            i = 0
            for devices in devices_list:
                # Only create 'complete' packing units
                if len(devices) != self.packing_size:
                    continue

                packing_unit_id = f"{lot_to_pack.identifier}_Pack{i}"

                # Collect all devices per lot and 'construct' input quantities
                input_devices = defaultdict(list)
                for d in devices:
                    input_devices[d[0]].append(d[1])

                child_quantities = [
                    {
                        "amount": len(d),
                        "class": lot.identifier,
                    }
                    for lot, d in input_devices.items()
                ]

                yield self.env.timeout(
                    0.1,
                    value={
                        "eventType": "Aggregation",
                        "action": "ADD",
                        "bizStep": "packing",
                        "parentEntity": packing_unit_id,
                        "childEntity": [lot.identifier for lot in input_devices.keys()],
                        "childQuantity": child_quantities,
                        "_devices": [d[1] for d in devices],
                    },
                )

                [self.remainder.remove(d) for d in devices]
                self.packing_units[f"{lot_to_pack.identifier}_Pack{i}"] = [
                    d[1] for d in devices
                ]
                i += 1
