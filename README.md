# Intro

This is an _unofficial_ Home Assistant component for use with Ensy InoVent.

If you have issues with the component, reach out in this GitHub repository, and not to Ensy.

When connected to WiFi, your Ensy aggregate will publish status to their service, and listen to control messages like adjusting fan speed and temperature. This component interacts with the same endpoint that their official iOS and Android apps communicate with.


# Prerequisites

Your Ensy AHU device must be connected and show the highlighted icon in the below image. The official app _must_ work before initial setup.

The addon author is not affiliated with Ensy, and has only tested this with an InoVent AHU-700BV.

![](static/connected_ensy_device.png)


# Usage

If you can use the official app, you should be able to add the component.

You only need the MAC-address to add the component. **Do not share your full MAC-address when reporting issues.**

If your Home Assistant server is on the same network as your Ensy aggregate, it might be auto-discovered. If it is not, please open an issue and provide only the first three pairs of your MAC-address – and _not_ the full MAC-address. I.e. `AB:CD:EF` and not `12:34:56` if your MAC is `AB:CD:EF:12:34:56`.


# Note on TLS security

The upstream Ensy endpoint this component interacts with is known to let its TLS certificate expire.

The component lets you disable TLS certificate validation for this reason. If you need to change the setting, you can reconfigure the component – and restart Home Assistant.


# Known Issues

## Reconfigure needs restart

If you reconfigure (to change MAC or change TLS security), you'll need to restart Home Assistant for the changes to take effect.

