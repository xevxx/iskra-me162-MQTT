**Daemon script to feed ISKRA ME162 data to MQTT**
===================================================

Forked and modifed from llagendijk/iskra-me162. 
This python script can run as a daemon and reads the usage data from an
ISKRA ME162 (will most likely work for other digital meters that have
an iec62056-21 interface.
The script was developed using a IR-head from 
http://wiki.volkszaehler.org/hardware/controllers/ir-schreib-lesekopf-usb-ausgang
Other IR-heads should work too, but have not yet been tested.
-Tested working with generic head reader from aliexpress

**Requirements**
------------
Python3 

**Usage:**
------
*iskra-me162*

**Configuration**
-------------
The package installs a configuration file in /etc/default/iskra-me162.
This file looks like:

::

	device_index = 54

	# port for ir-head

	port = "/dev/ttyUSB0"

	# use high speed: switch to high speed reading, may not work
	# Set True or False
	use_highspeed = False

	# print debug information?
	# 0 = no debug information printed
	# 1 = normal debug information printed
	# 2 = detailed information printed
	print_debug = 0

	# state file is often written, so on a raspberry pi make sure it
	# is on a memory back file system (tmpfs)
	state_file = "/var/run/me162-state"

	# interval for updating domoticz, recommend at least 60 seconds
	update_interval = 120

**Description of the options in the configuration file**
-----------------------------------------------------

Print_debug will enable debug printouts from the script so you can see what
happens.See the configuration file for a description of the possible values.

The script needs to maintain some state of the latest values sent to domoticz.
In order not to wear out the sd-card it is recommended to store the file on 
a tmpfs filesystem. If the statefile is not found (e.g. after a reboot) it will
be re-created.

The script is meant to be run  as a daemon. The update-interval determines
the frequency of the mqtt updates. A value of at least 60 seconds shall be
chosen. Recommended value: 120 (seconds)

**Systemd integration**
A systemd service file is included in the package. Execute the following to enable
the service:

::
	systemctl daemon-reload
	systemctl enable iskra-me162.service
	systemctl start iskra-me162.service

**Known problems**
--------------
The use_highspeed option, used to control the speed of the serial connection
does not always work. As the amount of data to be transferred is fairly small
I recommend leaving the serial speed at 300 baud (use_highspeed = False) so it always
works!

The values for current consumption and energy delivered are caculated from the
total consumption/delivered counters. They result is not very accurate.

**Feedback**
--------

Please send patches or bug reports to <louis.lagendijk@gmail.com>

**Source**
------

You can get a local copy of the development repository with::

    git clone git://github.com/xevxx/iskra-me162-MQTT


**License**
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
