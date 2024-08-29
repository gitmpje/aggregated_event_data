class ProductionLot:
    def __init__(
        self,
        identifier: str,
        required_steps: list,
        required_material: dict,
        devices: list,
        merge_configuration: dict = dict(),
        split_configuration: dict = dict(),
        executed_steps: list = None,
    ):
        self.identifier = identifier
        self.required_steps = required_steps
        self.required_material = required_material
        self.merge = merge_configuration
        self.split = split_configuration
        self.devices = devices

        self.executed_steps = executed_steps if executed_steps else []
        self.closed = False


class MaterialLot:
    def __init__(
        self,
        identifier: str,
        type: str,
        quantity: int,
    ):
        self.identifier = identifier
        self.type = type
        self.quantity = quantity
        self.closed = False
