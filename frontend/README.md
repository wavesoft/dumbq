
# DumbQ Front-End Library

This library can be used by any web application that interfaces with a VM that runs the `dumbq-client` script. It takes care of polling status information from the host and child VMs and firing the appropriate callback functions.

## How to use

After you have loaded the `dumbq.js` in your document a global class `DQFrontEnd` will become avaialble:

```html
<script type="text/javascript" src="/path/to/dumbq.min.js"></script>
```

You will need to instance it and activate it when you know what's the base URL of the VM. To do so, call the `activate( baseURL )` function:

```javascript
// Instantiate a new DumbQ Front-End monitor
var dqfe = new DQFrontEnd();

// To activate polling, just point on the base URL exposed by the VM
dqfe.activate("http://127.0.0.1:4128/");
```

## Handling Events

The library will fire a variety of events. To listen for them, use jQuery's `.on()` function, like so:

```javascript
dqfe.on('online', function(event, machine) {
    alert('Machine '+machine['vmid']+' is now online!');
});
```

The following sections contain a list of events triggered by the `dumbq.js` library.

### created.instance( `event`, `{ instance }` )

A new instance was created. You can find all the information about the new instance in the `instance` object. When the job makes available the first metrics, the event `online.instance` will be fired.

### destroyed.instance( `event`, `{ instance }` )

An instance has been destroyed. You can find all the details of the instance up to the time it became unavailable in the `instance` object.

### offline.instance( `event`, `{ instance }` )

An instance has gone offline (ex. finished it's job and exited). You can find all the details of the instance up to the time it became unavailable in the `instance` object.

### online.instance( `event`, `{ instance }` )

An instance has become online. You can find all the details of the instance up to the time it became unavailable in the `instance` object.

### metrics.instance( `event`, `{ metrics }`, `{ instance }` )

The metrics of the specified `instance` object have been updated. The latest values are available in the `metrics` object.

### offline( `event` )

The connection to the Virtual Machine has been interrupted.

### online( `event`, `{ machine }` )

The library successfully connected to the Virtual Machine. The details about the VM can be found in the `machine` object.

## High-Level Events

In addition to the low-level events mentioned above, the `dumbq.js` library also calculate accumulated metrics for all the instances, and fire the following callbacks.

### metrics.details( `event`, `{ metrics }` )

The `metrics` object provides overall details of the status of the instance and it contains the following fields:

<table>
    <tr>
        <th>Field</th>
        <th>Type</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><code>progress</code></td>
        <td>float</td>
        <td>A number between 0.0 to 1.0, indicating what's the overall progress of the tasks the machine is currently running. This value is averaged in case of more than one concurrently active workers.</td>
    </tr>
    <tr>
        <td><code>activity</code></td>
        <td>float</td>
        <td>A number between 0.0 to 1.0, indicating what's the current machine activity. That's equal to unix CPU load but up until 1.0.</td>
    </tr>
    <tr>
        <td><code>load</code></td>
        <td>float</td>
        <td>The actual 5-minute CPU load of the machine.</td>
    </tr>
    <tr>
        <td><code>uptime</code></td>
        <td>float</td>
        <td>A number indicating how many seconds the machine have been running.</td>
    </tr>
    <tr>
        <td><code>idletime</code></td>
        <td>float</td>
        <td>A number indicating how many seconds the machine have been idle.</td>
    </tr>
    <tr>
        <td><code>runhours</code></td>
        <td>integer</td>
        <td>A number indicating how many hours the machine has been running, regardless of reboots.</td>
    </tr>
</table>

