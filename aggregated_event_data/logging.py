import logging
import os

logger = logging.getLogger()

from collections import defaultdict
from datetime import datetime, timedelta
from json import dump
from functools import partial, wraps
from pathlib import Path
from simpy import Environment


from aggregated_event_data.production_entities import Lot
from aggregated_event_data.production_resources import ProductionResource

DEFAULT_LOGS_FOLDER = Path(__file__).parent.parent.joinpath("logs")


class SimulationEventLogging:
    def __init__(
        self,
        env: Environment,
        identifier: str,
        event_log_file: str = None,
        timeunit: str = "MINUTES",
        initial_time: datetime = datetime(2025, 1, 1),
    ):
        self.env = env
        self.identifier = identifier
        self.initial_time = initial_time
        self.timeunit = timeunit
        self.time_format = "%Y-%m-%dT%H:%M:%S.%fZ"

        if event_log_file:
            self.event_log_file = event_log_file
            self.events_file = f"{event_log_file}_events.txt"
        else:
            self.event_log_file = os.path.join(
                DEFAULT_LOGS_FOLDER, f"{self.identifier}_event_log.json"
            )
            self.events_file = os.path.join(
                DEFAULT_LOGS_FOLDER, f"{self.identifier}_events.txt"
            )

        self.aggregated_entities = set()
        self.production_resources = set()
        self.products = set()

        # Clear event log
        with open(self.events_file, "w") as f:
            f.write("")

        # Capture event data
        self.json_ld_events = []
        self.ocel_events = []

        # Bind *data* as first argument to monitor()
        # see https://docs.python.org/3/library/functools.html#functools.partial
        monitor = partial(self.monitor, self.json_ld_events, self.ocel_events)
        self.trace(env, monitor)

    def trace(self, env, callback):
        """Replace the ``step()`` method of *env* with a tracing function
        that calls *callbacks* with an events time, priority, ID and its
        instance just before it is processed.

        """

        def get_wrapper(env_step, callback):
            """Generate the wrapper for env.step()."""

            @wraps(env_step)
            def tracing_step():
                """Call *callback* for the next event if one exist before
                calling ``env.step()``."""
                if len(env._queue):
                    t, prio, eid, event = env._queue[0]
                    callback(t, prio, eid, event)
                return env_step()

            return tracing_step

        env.step = get_wrapper(env.step, callback)

    def displace(self, time: float) -> datetime:
        return self.initial_time + (
            timedelta(seconds=time)
            if self.timeunit == "SECONDS"
            else timedelta(minutes=time)
            if self.timeunit == "MINUTES"
            else timedelta(hours=time)
            if self.timeunit == "HOURS"
            else timedelta(days=time)
            if self.timeunit == "DAYS"
            else None
        )

    def monitor(self, json_ld_events, ocel_events, time, prio, eid, event):
        timestamp = self.displace(time).strftime(self.time_format)
        with open(self.events_file, "a") as f:
            f.write(f"{timestamp}: {str(event)}\n")

        if isinstance(event._value, dict):
            if "json-ld" in event._value:
                json_ld_dict = {"eventIdentifier": str(eid), "timestamp": timestamp}
                json_ld_dict.update(event._value["json-ld"])
                json_ld_events.append(json_ld_dict)

            if "ocel" in event._value:
                ocel_dict = {"id": str(eid), "time": timestamp}
                ocel_dict.update(event._value["ocel"])
                ocel_events.append(ocel_dict)

    def monitor_lot_store(env, store):
        while True:
            yield env.timeout(1)
            logger.info(env.now, " - lots in store: ", store.items)

    def register_aggregated_entity(self, entity: Lot):
        self.aggregated_entities.add(entity)

    def register_production_resource(self, resource: ProductionResource):
        self.production_resources.add(resource)

    def register_product(self, product: str):
        self.products.add(product)

    def write_json_event_data(self):
        aggregated_entities = [
            {
                "@type": ["AggregatedEntity", e.__class__.__name__],
                "identifier": e.identifier,
                "rdfs:label": e.identifier,
            }
            for e in self.aggregated_entities
        ]

        products = [
            {
                "@type": "Product",
                "identifier": p.identifier,
                "rdfs:label": p.identifier,
            }
            for p in self.products
        ]

        # Convert devices to dictionary
        for e in self.json_ld_events:
            e["_devices"] = [d.__dict__ for d in e["_devices"]]

        event_log = {
            "@context": {
                "@version": 1.1,
                "@base": "http://example.org/id/ekg/aggregated_traces/",
                "@vocab": "http://example.org/def/ekg/aggregated_traces/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "prov": "http://www.w3.org/ns/prov#",
                "events": {
                    "@container": "@set",
                    "@context": {
                        "eventIdentifier": "@id",
                        "eventType": "@type",
                        "entity": {"@type": "@id"},
                        "parentEntity": {"@type": "@id"},
                        "childEntity": {"@type": "@id"},
                        "location": {"@type": "@id"},
                        "_devices": {
                            "@id": "device",
                            "@container": "@set",
                            "@context": {
                                "identifier": "@id",
                                "materials": {
                                    "@id": "material",
                                    "@container": "@set",
                                    "@type": "@id",
                                },
                            },
                        },
                        "_materials": {"@id": "material", "@type": "@id"},
                        "class": {"@type": "@id"},
                    },
                },
                "entities": {"@container": "@set", "@context": {"identifier": "@id"}},
                "products": {"@container": "@set", "@context": {"identifier": "@id"}},
            },
            "events": self.json_ld_events,
            "entities": aggregated_entities,
            "products": products,
        }

        with open(self.event_log_file, "w") as f:
            dump(event_log, f, indent=2)

    def write_ocel_json(self, file_name):
        OCEL_ATTRIBUTE_TYPES = {
            str: "string",
            datetime: " time",
            int: "integer",
            float: "float",
            bool: "boolean",
        }

        def get_class_attributes(cls):
            attrs = []
            for base_cls in cls.__mro__:
                attrs.extend(
                    [
                        (key, OCEL_ATTRIBUTE_TYPES.get(type(value), "string"))
                        for key, value in vars(base_cls).items()
                        if not key.startswith("__") and not callable(value)
                    ]
                )
            return attrs

        def get_object_attributes(obj):
            attr_values = []
            for key, value in vars(obj).items():
                if key.startswith("__") or callable(value):
                    continue
                if type(value) not in OCEL_ATTRIBUTE_TYPES.keys():
                    value = str(value)
                attr_values.append((key, value))

            return attr_values

        # Collect event types and their attributes
        event_attributes = defaultdict(set)
        for e in self.ocel_events:
            event_attributes[e["type"]].update(
                [
                    (attr["name"], type(attr["value"]))
                    for attr in e.get("attributes", [])
                ]
            )

        event_types = [
            {
                "name": key,
                "attributes": [
                    {
                        "name": attr[0],
                        "type": OCEL_ATTRIBUTE_TYPES.get(attr[1], "string"),
                    }
                    for attr in attribute_set
                ],
            }
            for key, attribute_set in event_attributes.items()
        ]

        # Collect objects
        objects = self.production_resources.union(self.aggregated_entities)
        object_classes = set(type(e) for e in objects)

        object_types = []
        object_types_attributes = {}
        for cls in object_classes:
            object_types.append(
                {
                    "name": cls.__name__,
                    "attributes": [
                        {"name": attr, "type": dtype}
                        for attr, dtype in get_class_attributes(cls)
                    ],
                }
            )
            object_types_attributes[cls.__name__] = [
                attr_name for attr_name, _ in get_class_attributes(cls)
            ]

        objects = [
            {
                "id": obj.identifier,
                "type": type(obj).__name__,
                "attributes": [
                    {
                        "name": name,
                        "time": self.initial_time.strftime(self.time_format),
                        "value": value,
                    }
                    for name, value in get_object_attributes(obj)
                    if name
                    in object_types_attributes[
                        type(obj).__name__
                    ]  # only include attributes that are defined on class level
                ],
            }
            for obj in objects
        ]

        with open(file_name, "w") as f:
            dump(
                {
                    "eventTypes": event_types,
                    "objectTypes": object_types,
                    "events": self.ocel_events,
                    "objects": objects,
                },
                f,
                indent=2,
            )
