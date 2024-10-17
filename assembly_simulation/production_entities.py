from copy import deepcopy
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

        self.env.logging.register_aggregated_entity(self)

    def create(self, amount: int, devices: List[dict] = [], materials: List[str] = []):
        yield self.env.timeout(
            0,
            value={
                "eventType": "Object",
                "bizStep": "creating_class_instance",
                "entity": self.identifier,
                "quantity": {
                    "amount": amount,
                    "class": [
                        self.identifier,
                        self.get_lot_model().identifier,
                    ],
                },
                "_devices": deepcopy(devices),
                "_materials": materials.copy(),
            },
        )

    def get_lot_model(self) -> None:
        if hasattr(self, "material_type"):
            lot_model = Product(label=self.material_type, kind="material")
        elif hasattr(self, "executed_steps"):
            # Lot model is based on the operations executed on the lot
            # Excluding merge/split
            operations = set(self.executed_steps) - set(["merge", "split"])
            lot_model = Product(label="-".join(operations), kind="lotModel")
        else:
            raise AttributeError(f"Type of lot {self.identifier} is not defined!")

        self.env.logging.register_product(lot_model)
        return lot_model


class ProductionLot(Lot):
    def __init__(
        self,
        *args,
        required_steps: list,
        required_material: dict,
        devices: List[dict],
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

        self.env.process(self.create(len(self.devices), devices=self.devices))


class MaterialLot(Lot):
    def __init__(
        self,
        *args,
        material_type: str,
        quantity: int,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.material_type = material_type
        self.quantity = quantity

        self.materials = [f"{self.identifier}_Material{d}" for d in range(quantity)]

        self.env.process(self.create(self.quantity, materials=self.materials))


class PackingUnit(Lot):
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)


class Product:
    def __init__(
        self,
        label: str,
        kind: str,
    ) -> None:
        self.label = label
        self.kind = kind
        self.identifier = f"{kind}/{label}"


class Device:
    def __init__(
        self,
        identifier: str,
    ) -> None:
        self.identifier = identifier

        self.materials = []
        self.quality = 1
