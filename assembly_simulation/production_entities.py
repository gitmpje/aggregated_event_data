from simpy import Environment
from typing import List


class Lot:
    def __init__(
        self,
        env: Environment,
        identifier: str,
    ) -> None:
        self.env = env
        self.identifier = identifier
        self.closed = False

        self.env.logging.register_entity(self)

    def create(self, amount: int, devices: List[str] = []):
        yield self.env.timeout(
            0,
            value={
                "eventType": "Object",
                "bizStep": "creating_class_instance",
                "entity": self.identifier,
                "quantity": {
                    "amount": amount,
                    "class": self.identifier,
                },
                "_devices": devices,
            },
        )


class ProductionLot(Lot):
    def __init__(
        self,
        *args,
        required_steps: list,
        required_material: dict,
        devices: list,
        merge_configuration: dict = dict(),
        split_configuration: dict = dict(),
        executed_steps: list = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.required_steps = required_steps
        self.required_material = required_material
        self.merge = merge_configuration
        self.split = split_configuration
        self.devices = devices

        self.executed_steps = executed_steps if executed_steps else []

        self.env.process(self.create(len(self.devices), self.devices))


class MaterialLot(Lot):
    def __init__(
        self,
        *args,
        type: str,
        quantity: int,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.type = type
        self.quantity = quantity

        self.env.process(self.create(self.quantity))


class PackingUnit(Lot):
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
