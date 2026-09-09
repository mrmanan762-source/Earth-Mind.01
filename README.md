# EarthMind System Skeleton v0.1

EarthMind is an AI-driven agricultural architecture system.

## Directory Structure

```
.
├── README.md
├── main.py                     # Entry point wrapper
├── setup.py                    # Package configuration
├── app/                        # Application core setup & lifecycle
│   ├── __init__.py
│   ├── main.py                 # Application bootstrap & lifecycle execution
│   ├── lifecycle.py            # LifecycleManager for module registration/startup/shutdown
│   └── workflow.py             # WorkflowEngine for request routing
├── core/                       # Core system framework contracts
│   ├── config/                 # Application configuration settings
│   │   └── settings.py
│   ├── errors/                 # Exception hierarchy and error contracts
│   │   └── exceptions.py
│   ├── interfaces/             # Core contracts & protocols
│   │   ├── module.py           # ModuleInterface & DatabaseInterface protocols
│   │   └── services.py         # AI, Memory, Inspector service interfaces
│   ├── logging/                # Standard logging handler setup
│   │   └── logger.py
│   └── schemas/                # System request/response & error Pydantic models
│       ├── application.py
│       └── contracts.py
├── modules/                    # System modules (loosely coupled via interfaces)
│   ├── ai/                     # AI & Language services
│   ├── memory/                 # Short/Long-term Memory management
│   ├── ulpu/                   # ULPU processing module
│   ├── vision/                 # Vision & image processing models
│   ├── drone/                  # Drone flight & telemetry services
│   ├── data_training/          # Data ingestion, dataset building & model training
│   ├── database/               # SQLite prototype database implementation
│   ├── external_services/      # External API integrations
│   └── inspector/              # Compliance, rule checking & system inspector
├── models/                     # Model artifacts directory
├── data/                       # Data storage directory
└── tests/                      # Unit & integration tests
    ├── test_database.py
    ├── test_lifecycle.py
    ├── test_modules.py
    ├── test_schemas.py
    └── test_workflow.py
```

## Running the Application

To run the application entry point:
```bash
python3 main.py
```

## Running Tests

To run all unit tests with `pytest`:
```bash
python3 -m pytest
```
