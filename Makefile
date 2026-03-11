PYTHON_WEATHER := pyenv exec python
PYTHON_SERVER := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
CLI_MODULE := weather_app.cli
INTERVAL ?= $(shell $(PYTHON_SERVER) -c 'from constants import DEFAULT_INTERVAL_SECONDS; print(DEFAULT_INTERVAL_SECONDS)')
ITERATIONS ?= 1
PORT ?= 8889

.PHONY: help once periodic forever run-server install-server-deps


help:
	@echo "Usage:"
	@echo "  make once                    # run one fetch cycle"
	@echo "  make periodic                # run with INTERVAL and ITERATIONS"
	@echo "  make forever                 # run forever with INTERVAL"
	@echo "  make run-server              # run the live weather web server (aiohttp)"
	@echo "  make install-server-deps     # install Python server dependencies (aiohttp)"
	@echo ""
	@echo "Override variables:"
	@echo "  make once CITY=Delhi"
	@echo "  make periodic CITY=Mumbai INTERVAL=120 ITERATIONS=5"
	@echo "  make forever CITY=Chennai INTERVAL=$(INTERVAL)"
	@echo "  make run-server CITY=Dhaka INTERVAL=$(INTERVAL) PORT=$(PORT)"

once:
ifeq ($(origin CITY), undefined)
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --iterations 1
else
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --city "$(CITY)" --iterations 1
endif

periodic:
ifeq ($(origin CITY), undefined)
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --interval $(INTERVAL) --iterations $(ITERATIONS)
else
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --city "$(CITY)" --interval $(INTERVAL) --iterations $(ITERATIONS)
endif

forever:
ifeq ($(origin CITY), undefined)
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --interval $(INTERVAL)
else
	$(PYTHON_WEATHER) -m $(CLI_MODULE) --city "$(CITY)" --interval $(INTERVAL)
endif

install-server-deps:
	$(PYTHON_SERVER) -m pip install -r requirements.txt

run-server:
ifeq ($(origin CITY), undefined)
	$(PYTHON_SERVER) -m backend.server --interval $(INTERVAL) --port $(PORT)
else
	$(PYTHON_SERVER) -m backend.server --city $(CITY) --interval $(INTERVAL) --port $(PORT)
endif
