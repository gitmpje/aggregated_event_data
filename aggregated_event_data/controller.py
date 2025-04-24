import logging

from random import shuffle
from simpy import Environment, FilterStore, PriorityItem, Store
from typing import Dict

logger = logging.getLogger()

from aggregated_event_data.production_entities import (
    MergeConfiguration,
    ProductionLot,
    SplitConfiguration,
)


def partition_list(list_in: list, n: int):
    shuffle(list_in)
    return [list_in[i::n] for i in range(n)]


class Controller:
    def __init__(
        self,
        env: Environment,
        resources: Dict[str, list],
        lot_store: Store,
        packing_store: Store,
    ):
        self.env = env
        self.resources = resources
        self.lot_store = lot_store
        self.merge_store = FilterStore(env)  # merge to specific target lot
        self.merge_store_model = FilterStore(env)  # merge based on model
        self.packing_store = packing_store

        self.controller_running = env.process(self.running())

    def running(self):
        while True:
            lot_to_schedule = yield self.lot_store.get()
            last_executed_step = (
                lot_to_schedule.executed_steps[-1]
                if lot_to_schedule.executed_steps
                else ""
            )

            merge_config = lot_to_schedule.get_merge_after_step(last_executed_step)
            split_config = lot_to_schedule.get_split_after_step(last_executed_step)

            # Assume merge and split cannot happen after the same step
            if merge_config:
                # Lots are merged into the first lot in the list
                merge_lot_identifier = (
                    merge_config.lot_identifiers[0]
                    if merge_config.lot_identifiers
                    else None
                )

                if lot_to_schedule.identifier == merge_lot_identifier:
                    # If lot is target of merge, start merging process
                    self.env.process(
                        self.merge_lot_multiple(lot_to_schedule, merge_config)
                    )
                elif merge_lot_identifier:
                    # If lot has to be merged to specific lot, add to store
                    yield self.merge_store.put(lot_to_schedule)
                    lot_to_schedule.closed = True
                else:
                    # Check if there is a lot with the same model in the store
                    lots_same_model = [
                        lot
                        for lot in self.merge_store_model.items
                        if lot.get_lot_model().identifier
                        == lot_to_schedule.get_lot_model().identifier
                    ]
                    # Merge with one of the lots with the same model
                    if lots_same_model:
                        source_lot = yield self.merge_store_model.get(
                            lambda lot: lot.get_lot_model().identifier
                            == lot_to_schedule.get_lot_model().identifier
                        )
                        self.env.process(
                            self.merge_lots(
                                source_lot=source_lot, target_lot=lot_to_schedule
                            )
                        )
                    else:
                        # Otherwise, put it in the store
                        yield self.merge_store_model.put(lot_to_schedule)

            elif split_config:
                self.env.process(self.split_lot(lot_to_schedule, split_config))
                lot_to_schedule.closed = True

            elif lot_to_schedule.required_steps:
                self.env.process(self.schedule_lot(lot_to_schedule))

            else:
                self.packing_store.put(lot_to_schedule)
                lot_to_schedule.closed = True

    def schedule_lot(self, lot_to_schedule: ProductionLot):
        next_step = lot_to_schedule.required_steps.pop(0)

        # Simple heuristic to schedule the lot at the resource with the shortest queue
        min_len = 10000000
        for resource in self.resources[next_step]:
            if len(resource.queue.items) < min_len:
                selected_resource = resource
                min_len = len(resource.queue.items)

        yield selected_resource.queue.put(PriorityItem("P1", lot_to_schedule))

    def merge_lot_multiple(self, target_lot: ProductionLot, config: MergeConfiguration):
        for lot_id in config.lot_identifiers[1:]:
            source_lot = yield self.merge_store.get(
                lambda lot: lot.identifier == lot_id
            )
            self.env.process(
                self.merge_lots(source_lot=source_lot, target_lot=target_lot)
            )
        return

    def merge_lots(self, source_lot: ProductionLot, target_lot: ProductionLot):
        yield self.env.timeout(
            0.1,
            value={
                "eventType": "Aggregation",
                "action": "ADD",
                "parentEntity": target_lot.identifier,
                "childEntity": source_lot.identifier,
                "childQuantity": [
                    {
                        "amount": len(source_lot.devices),
                        "class": [
                            source_lot.identifier,
                            source_lot.get_lot_model().identifier,
                        ],
                    },
                    {
                        "amount": len(target_lot.devices),
                        "class": [
                            target_lot.identifier,
                            target_lot.get_lot_model().identifier,
                        ],
                    },
                ],
                "_devices": target_lot.devices + source_lot.devices,
            },
        )
        target_lot.devices.extend(source_lot.devices)
        source_lot.devices = []
        logger.info(
            f"{target_lot.identifier} [{self.env.now}] - Merged {source_lot.identifier}"
        )
        source_lot.executed_steps.append("merge")
        target_lot.executed_steps.append("merge")

        yield self.lot_store.put(target_lot)
        return

    def split_lot(self, target_lot: ProductionLot, config: SplitConfiguration):
        n = config.number_of_split_lots
        devices_list = partition_list(target_lot.devices, n)
        splitted_lots = []
        for i in range(n):
            # Do not create lots without devices
            if not devices_list[i]:
                continue

            lot = ProductionLot(
                env=self.env,
                identifier=f"{target_lot.identifier}_{i}",
                required_steps=target_lot.required_steps.copy(),
                required_material=target_lot.required_material.copy(),
                devices=devices_list[i],
                executed_steps=target_lot.executed_steps.copy(),
                merge_configs=target_lot.merge_configs,
                split_configs=target_lot.split_configs,
            )

            splitted_lots.append(lot)

        yield self.env.timeout(
            0.1,
            value={
                "eventType": "Aggregation",
                "action": "DELETE",
                "parentEntity": target_lot.identifier,
                "childEntity": [lot.identifier for lot in splitted_lots],
                "childQuantity": [
                    {
                        "amount": len(lot.devices),
                        "class": [
                            lot.identifier,
                            lot.get_lot_model().identifier,
                        ],
                    }
                    for lot in splitted_lots
                ],
                "_devices": target_lot.devices,
            },
        )

        logger.info(
            f"{target_lot.identifier} [{self.env.now}] - Splitted {[lot.identifier for lot in splitted_lots]}"
        )

        for lot in splitted_lots:
            [target_lot.devices.remove(d) for d in lot.devices]
            lot.executed_steps.append("split")
            yield self.lot_store.put(lot)

        target_lot.devices = []
        target_lot.executed_steps.append("split")
        return
