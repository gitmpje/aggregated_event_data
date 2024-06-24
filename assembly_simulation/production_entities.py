class ProductionLot:
    def __init__(
            self,
            identifier: str,
            required_steps: list,
            merge_configuration: dict,
            split_configuration: dict,
            devices: list,
            executed_steps: list = None
        ):

        self.identifier = identifier
        self.required_steps = required_steps
        self.merge = merge_configuration
        self.split = split_configuration
        self.devices = devices

        self.executed_steps = executed_steps if executed_steps else []
        self.closed = False