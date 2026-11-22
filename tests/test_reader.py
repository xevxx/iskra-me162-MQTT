import importlib.machinery
import importlib.util
import json
import pickle
import socket
import struct
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / "iskra-me162"
loader = importlib.machinery.SourceFileLoader("reader", str(script))
spec = importlib.util.spec_from_loader(loader.name, loader)
reader = importlib.util.module_from_spec(spec)
loader.exec_module(reader)

TELEGRAM = (
    b"\x02C.1.0(12345678)\r\n"
    b"1.8.0(0000001.001*kWh)\r\n1.8.1(0.290*kWh)\r\n1.8.2(0.711)\r\n"
    b"2.8.0(0000000.500*kWh)\r\n2.8.1(0*kWh)\r\n2.8.2(.500*kWh)\r\n"
    b"ignored ! line\r\n"
    b"!\r\n\x03"
)


class SerialHead:
    def __init__(self, incoming, *, trickle=False, disconnected=False):
        self.incoming = iter(incoming)
        self.trickle = trickle
        self.disconnected = disconnected
        self.baudrate = 300
        self.out_waiting = 0
        self.timeout = 0.1
        self.closed = False
        self.writes = []
        self.now = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def read(self, size):
        if self.disconnected:
            raise reader.serial.SerialException("disconnected")
        byte = next(self.incoming, None)
        if byte is None and not self.trickle:
            self.now += self.timeout
            return b""
        if self.trickle and self.timeout < 0.09:
            self.now += self.timeout
            return b""
        self.now += 0.09 if self.trickle else 0.01
        return bytes((byte if byte is not None else ord("x"),))

    def sleep(self, seconds):
        self.now += seconds

    def write(self, command):
        self.writes.append(command)
        return len(command)


class SerialTests(unittest.TestCase):
    def read(self, head, highspeed=False):
        config = SimpleNamespace(port="/fake", use_highspeed=highspeed)
        clock = SimpleNamespace(monotonic=lambda: head.now, time=time.time, sleep=head.sleep)
        with patch.object(reader.serial, "Serial", return_value=head), patch.object(reader, "time", clock):
            return reader.read_meter(config)

    def test_default_and_negotiated_speed_with_echoes(self):
        for highspeed, code, baud in ((False, b"0", 300), (True, b"5", 9600)):
            with self.subTest(highspeed=highspeed):
                ack = b"\x060" + code + b"0\r\n"
                head = SerialHead(b"/?!\r\nnoise/\r\n/ISK5ME162\r\n" + ack + TELEGRAM)
                result = self.read(head, highspeed)
                self.assertEqual(head.writes, [b"/?!\r\n", ack])
                self.assertEqual(head.baudrate, baud)
                self.assertTrue(head.closed)
                self.assertEqual(result["usage1"], 290)
                self.assertEqual(result["total_usage"], 1001)

    def test_silence_and_continuous_bytes_hit_the_same_deadline(self):
        for head in (
            SerialHead(b""),
            SerialHead(b"", trickle=True),
            SerialHead(b"/ISK5ME162\r\n" + TELEGRAM.split(b"\r\n!\r\n")[0], trickle=True),
        ):
            with self.subTest(trickle=head.trickle):
                with self.assertRaisesRegex(reader.MeterError, "Timed out"):
                    self.read(head)
                self.assertAlmostEqual(head.now, 30, places=6)
                self.assertTrue(head.closed)

    def test_invalid_registers_and_disconnect_then_recovery(self):
        for telegram, reason in (
            (TELEGRAM.replace(b"0.290*kWh", b"nan*kWh"), "Invalid value"),
            (TELEGRAM.replace(b"1.8.1(0.290*kWh)\r\n", b""), "Missing energy registers"),
            (TELEGRAM.replace(b"0.290*kWh", b"-0.290*kWh"), "Negative value"),
        ):
            with self.subTest(reason=reason):
                head = SerialHead(b"/ISK5ME162\r\n" + telegram)
                with self.assertRaisesRegex(reader.MeterError, reason):
                    self.read(head)
                self.assertTrue(head.closed)
        head = SerialHead(b"", disconnected=True)
        with self.assertRaises(reader.serial.SerialException):
            self.read(head)
        self.assertTrue(head.closed)
        self.assertEqual(self.read(SerialHead(b"/ISK5ME162\r\n" + TELEGRAM))["total_return"], 500)


def reading(timestamp, imported, exported):
    return {
        "time": timestamp, "serial": "12345678", "total_usage": imported,
        "total_return": exported, "usage1": imported, "usage2": 0,
        "return1": exported, "return2": 0,
    }


def receive_packet(stream):
    header = stream.read(1)[0]
    length = 0
    multiplier = 1
    while True:
        byte = stream.read(1)[0]
        length += (byte & 127) * multiplier
        if byte < 128:
            return header, stream.read(length)
        multiplier *= 128


class PublishTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = SimpleNamespace(**reader.DEFAULTS)
        self.config.broker_address = "127.0.0.1"
        self.config.client_name = "test-reader"
        self.config.broker_use_userpass = True
        self.config.broker_u = "test-user"
        self.config.broker_p = "test-password"
        self.state_path = Path(directory.name) / "state"
        self.config.state_file = self.state_path

    def exchange(self, current, previous, outcome):
        old_state = self.state_path.read_bytes() if self.state_path.exists() else None

        def broker(listener):
            peer, _ = listener.accept()
            with peer, peer.makefile("rb") as stream:
                peer.settimeout(2)
                header, body = receive_packet(stream)
                self.assertEqual(header, 0x10)
                self.assertTrue(body.endswith(b"\x00\x0btest-reader\x00\x09test-user\x00\x0dtest-password"))
                if outcome == "reject":
                    peer.sendall(b"\x20\x02\x00\x05")
                    return
                if outcome == "no_connack":
                    stream.read()
                    return
                peer.sendall(b"\x20\x02\x00\x00")
                header, body = receive_packet(stream)
                self.assertEqual(header, 0x32)  # PUBLISH, QoS 1
                size = struct.unpack("!H", body[:2])[0]
                self.assertEqual(body[2:2 + size], b"meter/me162/readings")
                message_id = body[2 + size:4 + size]
                payload = json.loads(body[4 + size:])
                if outcome == "drop":
                    peer.shutdown(socket.SHUT_RDWR)
                    return
                if outcome == "ack":
                    actual_state = self.state_path.read_bytes() if self.state_path.exists() else None
                    self.assertEqual(actual_state, old_state)
                    peer.sendall(b"\x40\x02" + message_id)
                self.assertEqual(receive_packet(stream), (0xE0, b""))
                return payload

        with socket.socket() as listener, ThreadPoolExecutor(max_workers=1) as pool:
            listener.bind(("127.0.0.1", 0))
            listener.settimeout(2)
            listener.listen(1)
            self.config.broker_port = listener.getsockname()[1]
            server = pool.submit(broker, listener)
            with patch.object(reader, "read_meter", return_value=current), \
                    patch.object(reader, "MQTT_TIMEOUT", 0.25):
                baseline = reader.poll(self.config, previous)
            return baseline, server.result(timeout=2)

    def test_first_acknowledgement_establishes_baseline(self):
        current = reading(120, 1000, 500)
        baseline, payload = self.exchange(current, None, "ack")
        self.assertEqual(baseline, current)
        self.assertEqual(reader.load_baseline(self.state_path), current)
        self.assertEqual(payload["consumption"], 0)
        self.assertEqual(payload["production"], 0)

    def test_failed_attempts_keep_baseline_until_recovery(self):
        previous = reading(120, 1000, 500)
        reader.save_baseline(self.state_path, previous)
        old_state = self.state_path.read_bytes()
        for outcome in ("reject", "no_connack", "drop", "no_puback"):
            with self.subTest(outcome=outcome), self.assertLogs(reader.LOG, "WARNING"):
                baseline, _ = self.exchange(reading(180, 1050, 525), previous, outcome)
                self.assertEqual(baseline, previous)
                self.assertEqual(self.state_path.read_bytes(), old_state)
        current = reading(240, 1100, 550)
        baseline, payload = self.exchange(current, previous, "ack")
        self.assertEqual(baseline, current)
        self.assertEqual(reader.load_baseline(self.state_path), current)
        self.assertEqual(payload, {
            "usage1": 1.1, "usage2": 0, "return1": 0.55, "return2": 0,
            "total_usage": 1.1, "total_return": 0.55, "consumption": 3.0, "production": 1.5,
        })


class StateTests(unittest.TestCase):
    def test_legacy_pickle_and_corrupt_state(self):
        old_type = type("MeterReadings", (), {"__module__": "__main__"})
        old = old_type()
        old.__dict__.update(reading(120, 1000, 500))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state"
            with patch.object(sys.modules["__main__"], "MeterReadings", old_type, create=True):
                path.write_bytes(pickle.dumps(old, protocol=3))
            self.assertEqual(reader.load_baseline(path), vars(old))
            path.write_bytes(b"{truncated")
            with self.assertLogs(reader.LOG, "WARNING"):
                self.assertIsNone(reader.load_baseline(path))

    def test_failed_state_replace_leaves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state"
            previous = reading(120, 1000, 500)
            reader.save_baseline(path, previous)
            with patch.object(reader.os, "replace", side_effect=OSError("disk error")), \
                    self.assertLogs(reader.LOG, "WARNING"):
                reader.save_baseline(path, reading(240, 1100, 550))
            self.assertEqual(reader.load_baseline(path), previous)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_invalid_intervals_resets_and_meter_replacement(self):
        previous = reading(120, 1000, 500)
        for current in (
            reading(120, 1100, 550),
            reading(119, 1100, 550),
            reading(240, 100, 550),
            reading(240, 1100, 50),
            dict(reading(240, 1100, 550), serial="new meter"),
        ):
            with self.subTest(current=current):
                payload = reader.make_payload(current, previous)
                self.assertEqual(payload["consumption"], 0)
                self.assertEqual(payload["production"], 0)
