from random import expovariate, shuffle
from simpy import Environment, Interrupt, PriorityStore, Store

class ProductionResource:
    def __init__(
            self,
            env: Environment,
            identifier: str,
            capability: str,
            mean_duration: float,
            mean_breakdown: float,
            mean_repair: float,
            lot_store: Store
        ) -> None:

        self.env = env

        self.identifier = identifier
        self.capability = capability
        self.mean_duration = mean_duration
        self.mean_breakdown = mean_breakdown
        self.mean_repair = mean_repair
        self.lot_store = lot_store

        self.state = "Idle"
        self.queue = PriorityStore(env)
        self.processing_process = env.process(self.processing())
        self.breakdown_process = env.process(self.breakdown())

    def breakdown(self):
        while True:
            yield self.env.timeout(
                expovariate(1/self.mean_breakdown)
            )
            if self.state == "Processing":
                # Only break the machine if it is currently working
                print(f"{self.identifier} [{self.env.now}] - Breakdown")
                self.processing_process.interrupt()
                self.state = "Broken"

    def processing(self):
        # Start working on a production lot
        while True:
            priority_item = yield self.queue.get()
            lot = priority_item.item

            print(f"{self.identifier} [{self.env.now}] - Start processing {lot.identifier}")
            yield self.env.timeout(
                0,
                value={
                    "lot": lot.identifier,
                    "resource": self.identifier,
                    "eventType": "Start",
                    "_devices": lot.devices.copy()
                }
            )

            self.state = "Processing"
            done_in = expovariate(1/self.mean_duration)
            while done_in:
                start = self.env.now
                try:
                    yield self.env.timeout(
                        done_in,
                        value={
                            "lot": lot.identifier,
                            "resource": self.identifier,
                            "eventType": "Finish",
                            "_devices": lot.devices.copy()
                        }
                    )
                    print(f"{self.identifier} [{self.env.now}] - Finished processing {lot.identifier}")

                    done_in = 0  #set to 0 to exit while loop
                    self.state = "Idle"
                    lot.executed_steps.append(self.capability)
                    self.lot_store.put(lot)

                except Interrupt:
                    done_in -= self.env.now - start  #remaining process time
                    yield self.env.timeout(expovariate(1/self.mean_repair))
                    print(f"{self.identifier} [{self.env.now}] - Repaired")
                    self.state = "Processing"

class PackingResource:
    def __init__(
            self,
            env: Environment,
            packing_size: int,
            packing_store: Store
        ):

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
            self.remainder.extend(lot_to_pack.devices)

            devices_list = list(zip(*(iter(self.remainder),)*self.packing_size))
            i = 0
            for devices in devices_list:
                if len(devices) != self.packing_size:
                    continue
                yield self.env.timeout(
                    0,
                    value={
                        "lot": lot_to_pack.identifier,
                        "packingUnit": f"{lot_to_pack.identifier}_Pack{i}",
                        "eventType": "Pack",
                        "outputQuantity": len(devices),
                        "_devices": list(devices)
                    }
                )
                [self.remainder.remove(d) for d in devices]
                self.packing_units[f"{lot_to_pack.identifier}_Pack{i}"] = devices
                i += 1