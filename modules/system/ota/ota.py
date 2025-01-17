import asyncio
import async_helpers
from app import App
from esp32 import Partition
import machine
from app_components import layout, tokens
import network
import ota
import ntptime
import requests
import wifi
from system.eventbus import eventbus
from system.scheduler.events import RequestStopAppEvent
from events.input import BUTTON_TYPES, ButtonDownEvent


class OtaUpdate(App):
    def __init__(self):
        self.status = None
        super().__init__()
        self.status = layout.DefinitionDisplay("Status", "")
        self.old_version = layout.DefinitionDisplay("Current", "-")
        self.new_version = layout.DefinitionDisplay("New", "-")
        self.layout = layout.LinearLayout(
            [self.status, self.old_version, self.new_version]
        )
        self.layout.y_offset = 70
        self.task = None
        eventbus.on_async(ButtonDownEvent, self._button_handler, self)

    async def _button_handler(self, event):
        layout_handled = await self.layout.button_event(event)
        if not layout_handled:
            if BUTTON_TYPES["CANCEL"] in event.button:
                self.minimise()

    def minimise(self):
        # Close this app each time
        if self.task is not None:
            try:
                self.task.cancel()
            except Exception:
                pass
        eventbus.emit(RequestStopAppEvent(self))

    async def run(self, render_update):
        self.status.value = "Checking version"

        try:
            Partition(Partition.RUNNING)
            # current.get_next_update()
        except Exception:
            # Hitting this likely means your partition table is out of date or
            # you're missing ota_data_initial.bin
            # windfow.println("No OTA info!")
            # window.println("USB flash needed")
            self.minimise()
            return

        # lines = window.flow_lines("OTA requires a  charged battery.USB power is    insufficient.")
        # for line in lines:
        #    window.println(line)
        # window.println("")

        version = ota.get_version()
        if version == "HEAD-HASH-NOTFOUND":
            version = "Custom"
        self.old_version.value = version

        await render_update()

        await self.connect(render_update)
        await self.otaupdate(render_update)
        self.minimise()

    async def connect(self, render_update):
        # window = self.window
        # line = window.get_next_line()
        ssid = wifi.get_ssid()
        if not ssid:
            print("No WIFI config!")
            return

        if not wifi.status():
            wifi.connect()
            while True:
                self.status.value = f"Connecting to {ssid}"
                await render_update()

                if await wifi.async_wait():
                    # Returning true means connected
                    break

                if wifi.get_sta_status() == network.STAT_CONNECTING:
                    pass  # go round loop and keep waiting
                else:
                    wifi.disconnect()
                    wifi.connect()
        ntptime.settime()
        print("IP:")
        print(wifi.get_ip())

    async def otaupdate(self, render_update):
        # window = self.window
        # window.println()
        # line = window.get_next_line()
        self.confirmed = False

        retry = True
        self.status.value = "Searching for OTA"

        await render_update()

        while retry:
            # window.clear_from_line(line)
            self.task = async_helpers.unblock(
                requests.head,
                render_update,
                "https://github.com/emfcamp/badge-2024-software/releases/download/latest/micropython.bin",
                allow_redirects=False,
            )
            response = await self.task
            url = response.headers["Location"]

            self.task = async_helpers.unblock(
                requests.get,
                render_update,
                "https://api.github.com/repos/emfcamp/badge-2024-software/releases/tags/latest",
                headers={"User-Agent": "Badge OTA"},
            )
            notes = await self.task

            if notes.status_code == 200:
                release_notes = notes.json()["body"]
                release_notes = [
                    line.split("[")[0].strip() for line in release_notes.split("\n")
                ]
                release_notes = "\n".join(release_notes)
                self.notes = layout.DefinitionDisplay("Release notes", release_notes)
                self.layout.items.append(self.notes)

            try:
                result = await async_helpers.unblock(
                    ota.update,
                    render_update,
                    self.progress,
                    url,
                )
                retry = False
            except OSError as e:
                print("Error:" + str(e))
                self.status.value = f"Failed: {e}"
                result = False
            except Exception as e:
                print(e)
                raise

        if result:
            # window.println("Updated OK.")
            # window.println("Press [A] to")
            # window.println("reboot and")
            # window.println("finish update.")
            self.status.value = "Rebooting"
            await render_update()
            await asyncio.sleep(5)
            machine.reset()
        else:
            await render_update()
            await asyncio.sleep(5)
            self.minimise()
            print("Update cancelled")

    def progress(self, version, val):
        self.new_version.value = version

        if not self.confirmed:
            if len(version) > 0:
                self.new_version.value = version
                if version <= ota.get_version():
                    self.status.value = "No update needed"
                    return False

                print("New version:")
                print(version)
                # window.println()
                # line = window.get_next_line()
                # window.println("Press [A] to")
                # window.println("confirm update.")
                # if not self.wait_for_a():
                #    print("Cancelling update")
                #    return False

                # Clear confirmation text
                # window.set_next_line(line)
            self.confirmed = True
            # window.println("Updating...")
            # window.println()

        self.progress_pct = val
        self.status.value = f"Downloading ({val} %)"
        return True

    def draw(self, ctx):
        # print("draw")
        tokens.clear_background(ctx)
        self.layout.draw(ctx)
