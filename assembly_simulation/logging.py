import os
from pathlib import Path

from json import dump
from simpy import Environment

from functools import partial, wraps

from assembly_simulation.production_entities import Lot

DEFAULT_LOGS_FOLDER = Path(__file__).parent.parent.joinpath("logs")


class SimulationEventLogging:
    def __init__(self, env: Environment, identifier: str, event_log_file: str = None):
        self.env = env
        self.identifier = identifier

        self.events_file = os.path.join(
            DEFAULT_LOGS_FOLDER, f"{self.identifier}_events.txt"
        )
        if event_log_file:
            self.event_log_file = event_log_file
        else:
            self.event_log_file = os.path.join(
                DEFAULT_LOGS_FOLDER, f"{self.identifier}_event_log.json"
            )

        self.aggregated_entities = set()
        self.products = set()

        # Clear event log
        with open(self.events_file, "w") as f:
            f.write("")

        # Capture event data
        self.event_list = []
        # Bind *data* as first argument to monitor()
        # see https://docs.python.org/3/library/functools.html#functools.partial
        monitor = partial(self.monitor, self.event_list)
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

    def monitor(self, event_list, t, prio, eid, event):
        with open(self.events_file, "a") as f:
            f.write(f"{t}: {str(event)}\n")
        if isinstance(event._value, dict):
            event_dict = {"eventIdentifier": str(eid), "timestamp": t}
            event_dict.update(event._value)
            event_list.append(event_dict)

    def monitor_lot_store(env, store):
        while True:
            yield env.timeout(1)
            print(env.now, " - lots in store: ", store.items)

    def register_aggregated_entity(self, entity: Lot):
        self.aggregated_entities.add(entity)

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
        for e in self.event_list:
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
            "events": self.event_list,
            "entities": aggregated_entities,
            "products": products,
        }

        with open(self.event_log_file, "w") as f:
            dump(event_log, f, indent=2)
