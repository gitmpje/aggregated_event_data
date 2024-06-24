from random import shuffle
from simpy import Environment, FilterStore, PriorityItem, Store
from typing import Dict

from assembly_simulation.production_entities import ProductionLot


def partition_list(list_in: list, n: int):
    shuffle(list_in)
    return [list_in[i::n] for i in range(n)]


class Controller:
    def __init__(
        self,
        env: Environment,
        resources: Dict[str, list],
        lot_store: Store,
        packing_store: Store
    ):

        self.env = env
        self.resources = resources
        self.lot_store = lot_store
        self.merge_store = FilterStore(env)
        self.packing_store = packing_store

        self.controller_running = env.process(self.running())

    def running(self):
        while True:
            lot_to_schedule = yield self.lot_store.get()

            if not lot_to_schedule.executed_steps and lot_to_schedule.required_steps:
                self.env.process(self.lot_scheduling(lot_to_schedule))

            # Assume merge and split cannot happen after the same step
            elif lot_to_schedule.executed_steps[-1] == lot_to_schedule.merge.get("after_step"):
                # Lots are merged into the first lot in the list
                if lot_to_schedule.identifier == lot_to_schedule.merge["lot_identifiers"][0]:
                    self.env.process(self.lot_merging(lot_to_schedule))
                else:
                    yield self.merge_store.put(lot_to_schedule)
                    lot_to_schedule.closed = True

            elif lot_to_schedule.executed_steps[-1] == lot_to_schedule.split.get("after_step"):
                self.env.process(self.lot_splitting(lot_to_schedule))
                lot_to_schedule.closed = True

            elif lot_to_schedule.required_steps:
                self.env.process(self.lot_scheduling(lot_to_schedule))

            else:
                self.packing_store.put(lot_to_schedule)
                lot_to_schedule.closed = True

    def lot_scheduling(self, lot_to_schedule: ProductionLot):
        next_step = lot_to_schedule.required_steps.pop(0)

        # Simple heuristic to schedule the lot at the resource with the shortest queue
        min_len = 10000000
        for resource in self.resources[next_step]:
            if len(resource.queue.items) < min_len:
                selected_resource = resource
                min_len = len(resource.queue.items)

        yield selected_resource.queue.put(PriorityItem("P1", lot_to_schedule))

    def lot_merging(self, target_lot: ProductionLot):
        for lot_id in target_lot.merge["lot_identifiers"][1:]:
            lot = yield self.merge_store.get(lambda lot: lot.identifier == lot_id)
            yield self.env.timeout(
                0.1,
                value={
                    "lot": target_lot.identifier,
                    "childLot": lot.identifier,
                    "eventType": "Merge",
                    "inputQuantity": [
                        {
                            "amount": len(target_lot.devices),
                            "class": "_".join(lot.executed_steps),
                            "fromEntity": target_lot.identifier,
                        },{
                            "amount": len(lot.devices),
                            "class": "_".join(lot.executed_steps),
                            "fromEntity": lot.identifier,
                        }
                    ],
                    "outputQuantity": {
                        "amount": len(target_lot.devices) + len(lot.devices),
                        "class": "_".join(target_lot.executed_steps),
                        "fromEntity": target_lot.identifier,
                    },
                    "_devices": target_lot.devices + lot.devices
                }
            )
            target_lot.devices.extend(lot.devices)
            lot.devices = []
            print(f"{target_lot.identifier} [{self.env.now}] - Merged {lot.identifier}")

        yield self.lot_store.put(target_lot)

    def lot_splitting(self, target_lot: ProductionLot):
        n = target_lot.split["number_of_split_lots"]
        devices_list = partition_list(target_lot.devices, n)
        splitted_lots = []
        for i in range(target_lot.split["number_of_split_lots"]):
            # Do not create lots without devices
            if not devices_list[i]:
                continue

            lot = ProductionLot(
                f"{target_lot.identifier}_{i}",
                target_lot.required_steps.copy(),
                dict(),
                dict(),
                devices_list[i],
                target_lot.executed_steps.copy()
            )

            splitted_lots.append(lot)

        yield self.env.timeout(
            0.1,
            value={
                "lot": target_lot.identifier,
                "childLot": [lot.identifier for lot in splitted_lots],
                "eventType": "Split",
                "inputQuantity": {
                    "amount": len(target_lot.devices),
                    "class": "_".join(target_lot.executed_steps),
                    "fromEntity": target_lot.identifier,
                },
                "outputQuantity": [
                    {
                        "amount": len(lot.devices),
                        "class": "_".join(lot.executed_steps),
                        "fromEntity": lot.identifier,
                    }
                    for lot in splitted_lots
                ],
                "_devices": target_lot.devices
            }
        )

        print(f"{target_lot.identifier} [{self.env.now}] - Splitted {[lot.identifier for lot in splitted_lots]}")

        for lot in splitted_lots:
            [target_lot.devices.remove(d) for d in lot.devices]
            yield self.lot_store.put(lot)

        target_lot.devices = []