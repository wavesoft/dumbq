
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

