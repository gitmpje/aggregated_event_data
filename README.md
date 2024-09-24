# aggregated_event_data

Package for simulating an (assembly) environment where products/devices are traced on an aggregated level.


## Features

### Production Entity

### Production Resources
* Each resource can execute one type of production step (or has one capability)
* Process time is exponentially distributed, with a fixed mean per resource. The process time is (currently) independent of the number of devices processed.

### Production entities
* Lot type is based on the operations executed on the lot.

#### Material Lots
* Shared store with material lots where all production resources have access to.
* Each device 'consumes' one unit of material at a production step.

### Controller
* Uses simple heuristic to schedule each lot at a resource with the shortest queue.

### Logging
* The logging is based on the EPCIS 2.0 vocabulary.


<!-- ### Project Structure -->


<!-- ## License -->


## Dependencies

This package requires the following Python packages to be installed for usage. These dependencies are listed in
`pyproject.toml` to be fetched automatically when installing with `pip`:
* `simpy` and its dependencies (BSD 3-clause License)


## Getting Started

### Installation

You can install this package using pip:

```bash
pip install -r requirements.txt
```


### Example

Example usage `python -m assembly_simulation.simulate examples/example_1.json`.


## Contributing

If you would like to contribute, please get in touch with us: mark.van.der.pas@semaku.com


<!-- ### Codestyle and Testing

Our code follows the [PEP 8 -- Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/).
Additionally, we use [PEP 484 -- Type Hints](https://www.python.org/dev/peps/pep-0484/) throughout the code to enable type checking the code.


### Contribute Code/Patches

TBD -->