all: distribution install

distribution: setup.py CloudWatcher/*
	python setup.py check
	python setup.py sdist
	python setup.py bdist_wheel --universal

install:
	apt -y update
	apt -y install python3-serial python3-paho-mqtt
	pip3 install . --break-system-packages
	cp -a etc/* /etc/

clean:
	pip3 uninstall --yes CloudWatcher
