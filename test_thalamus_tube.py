"""Small-piece checks of the Thalamus as the tube with a volume knob.

These only catch breakage in the carrying itself. Whether she works is
judged by booting her and reading the trace (CLAUDE.md).
"""

from __future__ import annotations

import threading
import time

from thalamus import Thalamus


class Lobe:
    def __init__(self, thalamus, handler=None, hears=()):
        self.thalamus = thalamus
        self.handler = handler
        self.hears = hears
        self.got = []

    def on_joined(self, name):
        self.name = name
        for topic in self.hears:
            self.thalamus.listen(name, topic)

    def process_message(self, message):
        self.got.append((message["type"], message["content"]))
        if self.handler is not None:
            return self.handler(self, message)
        return {"status": "success", "content": {"ok": True}}


def test_thalamus_has_no_turn_script_and_holds_nothing():
    t = Thalamus()
    for gone in ("process_user_input", "process_sensory_input", "notus_fallback", "last_output_envelope"):
        assert not hasattr(t, gone)


def test_announcement_reaches_every_listener_and_failure_is_reported():
    t = Thalamus()
    a, b = Lobe(t, hears=("news",)), Lobe(t, hears=("news",))
    t.register_lobe("a", a)
    t.register_lobe("b", b)
    t.announce("news", {"n": 1}, source="someone")
    assert t.wait_until_quiet(5)
    assert a.got == [("news", {"n": 1})] and b.got == [("news", {"n": 1})]
    missing = t.send_and_wait("nobody", "hello", {})
    assert missing["status"] == "error" and "nobody" in missing["message"]
    t.shutdown()


def test_two_lobes_waiting_on_each_other_do_not_lock_up():
    t = Thalamus()

    def a_handler(lobe, message):
        if message["type"] == "start":
            time.sleep(0.05)  # so b is already waiting on a
            return t.send_and_wait("b", "question_for_b", {}, source="a")
        return {"status": "success", "content": {"from": "a"}}

    def b_handler(lobe, message):
        if message["type"] == "start":
            time.sleep(0.05)
            return t.send_and_wait("a", "question_for_a", {}, source="b")
        return {"status": "success", "content": {"from": "b"}}

    t.register_lobe("a", Lobe(t, a_handler, hears=("start",)))
    t.register_lobe("b", Lobe(t, b_handler, hears=("start",)))
    started = time.monotonic()
    t.announce("start", {}, source="someone")
    assert t.wait_until_quiet(10)
    assert time.monotonic() - started < 5, "the two lobes locked up until the answer timeout"
    kinds_a = [k for k, _ in t.inboxes["a"].lobe.got]
    kinds_b = [k for k, _ in t.inboxes["b"].lobe.got]
    assert "question_for_a" in kinds_a and "question_for_b" in kinds_b
    t.shutdown()


def test_a_lobe_finishes_what_it_is_doing_before_an_unrelated_ask():
    """An ask from another lobe doesn't cut into a lobe that is waiting on a third."""
    t = Thalamus()
    order = []

    def busy_handler(lobe, message):
        if message["type"] == "work":
            order.append("work starts")
            t.send_and_wait("slow", "take_time", {}, source="busy")
            order.append("work ends")
        else:
            order.append(message["type"])
        return {"status": "success", "content": {}}

    def slow_handler(lobe, message):
        time.sleep(0.15)
        return {"status": "success", "content": {}}

    t.register_lobe("busy", Lobe(t, busy_handler, hears=("work",)))
    t.register_lobe("slow", Lobe(t, slow_handler))
    t.register_lobe("other", Lobe(t))
    t.announce("work", {}, source="someone")
    time.sleep(0.05)
    asker = threading.Thread(target=lambda: t.send_and_wait("busy", "unrelated_ask", {}, source="other"))
    asker.start()
    asker.join(5)
    assert order == ["work starts", "work ends", "unrelated_ask"]
    t.shutdown()


def test_only_attention_sets_the_volume_and_louder_goes_first_nothing_dropped():
    t = Thalamus()
    release = threading.Event()

    def listener_handler(lobe, message):
        if message["type"] == "hold":
            release.wait(5)
        return {"status": "success", "content": {}}

    def attention_handler(lobe, message):
        return t.set_volume(message["content"])

    def speaker_handler(lobe, message):
        t.tell("listener", message["content"]["say"], {}, source=lobe.name)
        return {"status": "success", "content": {}}

    listener = Lobe(t, listener_handler)
    t.register_lobe("listener", listener)
    t.register_lobe("attention", Lobe(t, attention_handler))
    t.register_lobe("quiet_one", Lobe(t, speaker_handler))
    t.register_lobe("loud_one", Lobe(t, speaker_handler))

    refused = t.set_volume({"from:loud_one": 2.0})  # not Attention asking
    assert refused["status"] == "error" and not t.volume

    assert t.send_and_wait("attention", "set", {"from:loud_one": 2.0})["status"] == "success"
    t.tell("listener", "hold", {})           # the listener is busy
    time.sleep(0.05)
    t.send_and_wait("quiet_one", "speak", {"say": "first_sent"})
    t.send_and_wait("loud_one", "speak", {"say": "second_sent_but_louder"})
    release.set()
    assert t.wait_until_quiet(5)
    kinds = [k for k, _ in listener.got]
    assert kinds == ["hold", "second_sent_but_louder", "first_sent"]  # louder first, nothing dropped
    t.shutdown()
