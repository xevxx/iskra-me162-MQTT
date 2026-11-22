ISKRA ME162 MQTT reader
======================

This daemon reads the ISKRA ME162 electricity meter through a USB optical
head and publishes its energy readings to MQTT.

Installation
------------

Use Python 3.8 or newer. On Raspberry Pi OS or another systemd distribution,
install the reader in a virtual environment. The package installs pySerial
and supports Paho MQTT 1.6 and 2.x. From the checkout, run::

    sudo python3 -m venv /opt/iskra-me162
    sudo /opt/iskra-me162/bin/python -m pip install .
    sudo ln -s /opt/iskra-me162/bin/iskra-me162 /usr/local/bin/iskra-me162

For a new installation, copy the sample configuration::

    sudo install -m 0600 iskra-me162.config /etc/default/iskra-me162.config

Set ``broker_address`` to your MQTT broker's hostname or IP address, and set
``port`` to your optical head's device path. The MQTT port defaults to 1883.
If the broker requires credentials, set ``broker_use_userpass = True`` and
fill in ``broker_u`` and ``broker_p``. Use a distinct ``client_name`` for each reader
connected to the same broker.

The configuration file uses Python syntax and runs at startup. Keep it
writable only by the administrator. Leave ``use_highspeed = False`` for 300 baud
unless your optical head works reliably at the speed advertised by the meter.
The default polling interval is 120 seconds. Set ``print_debug = 2`` for more
detail in the journal.

To install and start the service::

    sudo install -m 0644 iskra-me162.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now iskra-me162.service
    sudo journalctl -u iskra-me162.service -f

Upgrading
---------

Keep your existing ``/etc/default/iskra-me162.config`` and state file. Before
replacing the script, move any broker settings or topic prefix you edited in
it into the configuration file. If an older installation put the executable
directly at ``/usr/local/bin/iskra-me162``, replace it with the virtual
environment symlink after backing up the old script.
Install the updated unit and restart the service::

    sudo install -m 0644 iskra-me162.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl restart iskra-me162.service

MQTT readings
-------------

The reader publishes JSON on ``meter/me162/readings`` by default. The
``msg_prefix`` setting controls the part of the topic before ``readings``.

- ``usage1``, ``usage2``, ``return1``, ``return2``, ``total_usage``, and ``total_return``
  are cumulative energy counters in kWh.
- ``consumption`` and ``production`` are average import and export power in kW
  since the last acknowledged reading. Both are zero when there is no usable
  baseline, such as on first run or after a counter reset.

The reader requests a broker acknowledgement using MQTT QoS 1. During an
outage it keeps the last acknowledged baseline. The first successful message
after recovery carries the latest totals and rates averaged over the elapsed
interval. QoS 1 can produce duplicates when an acknowledgement goes missing.

The default state file is ``/var/run/me162-state``. A reboot may clear it when
``/var/run`` is on tmpfs. The reader can load state from the old script and
writes the next acknowledged baseline in JSON.

License
-------

Copyright (C) 2016 Louis Lagendijk <louis.lagendijk@gmail.com>
Based on previous work by J. Jeurissen and J. van der Linde ((c) 2012/2013)
updates for MQTT by xevxx 2023

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
