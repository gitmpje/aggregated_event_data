import os

from json import dump
from simpy import Environment

from functools import partial, wraps

LOGS_FOLDER = "logs"

class SimulationEventLogging:

    def __init__(self, env: Environment):
        self.env = env

        # Clear event log
        with open(os.path.join(LOGS_FOLDER, "events.txt"), "w") as f:
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
        with open(os.path.join(LOGS_FOLDER, "events.txt"), "a") as f:
            f.write(f"{t}: {str(event)}\n")
        if isinstance(event._value, dict):
            event_dict = {"eventIdentifier": str(eid), "timestamp": t}
            event_dict.update(event._value)
            event_list.append(event_dict)

    def monitor_lot_store(env, store):
        while True:
            yield env.timeout(1)
            print(env.now, " - lots in store: ", store.items)

    def write_json_event_data(self):

        event_log = {
            "@context": {
                "@version": 1.1,
                "@base": "http://example.org/id/event/",
                "@vocab": "http://example.org/def/event/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "prov": "http://www.w3.org/ns/prov#",
                "events": {
                    "@container": "@list",
                    "@context": {
                        "eventIdentifier": "@id",
                        "eventType": "@type",
                        "timestamp": "prov:atTime",
                        "lot": {
                            "@id": "prov:entity",
                            "@type": "@id"
                        },
                        "resource": {
                            "@id": "prov:entity",
                            "@type": "@id"
                        }
                    }
                }
            },
            "events": self.event_list
        }

        with open("logs/event_log.json", "w") as f:
            dump(event_log, f, indent=2)