import os

from json import dump
from simpy import Environment

from functools import partial, wraps

LOGS_FOLDER = "logs"
ENTITY_PATHS = [
    "entity",
    "parentEntity",
    "childEntity",
    "inputQuantity.class",
    "outputQuantity.class",
]


class SimulationEventLogging:
    def __init__(self, env: Environment, identifier: str):
        self.env = env
        self.identifier = identifier
        self.events_file = os.path.join(LOGS_FOLDER, f"{self.identifier}_events.txt")
        self.event_log_file = os.path.join(
            LOGS_FOLDER, f"{self.identifier}_event_log.json"
        )

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

    def get_entities(self, event_dict):
        entities = []
        for path in ENTITY_PATHS:
            v = event_dict
            for k in path.split("."):
                if isinstance(v, list):
                    for i in v:
                        entities.append(i[k])
                else:
                    v = v.get(k)
                    if not v:
                        break
                    elif isinstance(v, str):
                        entities.append(v)
        return entities

    def write_json_event_data(self):
        aggregated_entities = []
        for event in self.event_list:
            aggregated_entities.extend(self.get_entities(event))

        aggregated_entities = [
            {"@type": "AggregatedEntity", "identifier": e, "rdfs:label": e}
            for e in set(aggregated_entities)
        ]

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
                        "_devices": {"@id": "device", "@type": "@id"},
                        "class": {"@type": "@id"},
                    },
                },
                "entities": {"@container": "@set", "@context": {"identifier": "@id"}},
            },
            "events": self.event_list,
            "entities": aggregated_entities,
        }

        with open(self.event_log_file, "w") as f:
            dump(event_log, f, indent=2)
