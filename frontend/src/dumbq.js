
/*! DumbQ API v1.0 | Ioannis Charalampidis, Citizen Cyberlab EU Project | GNU GPL v2.0 License */

/**
 * Pick an initiator function according to AMD or stand-alone loading
 */
( window.define == undefined ? function(req, fn) { window.DumbQ = fn($ || jQuery); } : window.define )(["jquery"], function($) {

	/**
	 * Check if jQuery requirement was not available as expected.
	 */
	if (!$) {
		console.error("CreditPiggy: jQuery must available in order to use creditpiggy.js!");
		return null;
	}

	/**
	 * DumbQ Namespace
	 */
	var DumbQ = {

	};

	/**
	 * DumbQ Front-End Interface
	 *
	 * This class will automatically interface to a running instance of DumbQ
	 * and fire appropriate callbacks upon state changes.
	 *
	 * Therefore it makes it easy to monitor arbitrary DumbQ instances.
	 *
	 */
	var DQFrontEnd = DumbQ.Frontend = function() {
		
		// Config parameters
		this.baseUrl = null;
		this.pollTimer = null;
		this.pollActive = false;
		this.disabled = true;

		// State information
		this.offline = true;
		this.seq_id = 0;
		this.machine = { };
		this.index = { };
		this.instances = [ ];

		// A flag that indicates if a summarization was performed
		this.summarised = false;

	}

	/**
	 * Check if two object properties are the same
	 */
	DQFrontEnd.prototype.__same = function( a, b ) {

		// Check for undefined match
		if ((a == undefined) && (b == undefined)) return true;
		if ((a == undefined) || (b == undefined)) return false;

		// Check if properties of 'a' do not exist in 'b'
		// and for the ones found common, check if they match
		for (var k in a) {
			if (a.hasOwnProperty(k)) {
				if (b.hasOwnProperty(k)) {
					// Property types do not match? return
					if (typeof(a[k]) != typeof(b[k])) return false;
					// If properties are objects, perform nested __same call
					if (typeof(a[k] == 'object'))
						if (!this.__same(a[k], b[k])) return false;
					// Otherwise if values are not the same, return false
					if (a[k] != b[k]) return false;
				} else {
					// Property of 'a' not in 'b'				
					return false
				}
			}
		}

		// If for any reason a property of b is 
		// not in a, quit anyways.
		for (var k in b)
			if (b.hasOwnProperty(k) && !a.hasOwnProperty(k))
				return false;

		// All checks passed
		return true;

	}

	/**
	 * Mark an instance as 'offline'
	 */
	DQFrontEnd.prototype.__markOfflineInstance = function( instance ) {

		// If instance was already offline, return
		if (instance['offline']) 
			return;

		// Trigger offline event
		instance['offline'] = true;
		$(this).triggerHandler('offline.instance', [ instance ]);

	}

	/**
	 * Update summarisation information
	 */
	DQFrontEnd.prototype.__updateSummarization = function() {

		// Progress summarization
		var progress = 0,
			progressCount = 0;

		// Iterate over instances
		for (var i=0; i<this.instances.length; i++) {
			var instance = this.instances[i];

			// Skip offline nodes
			if (instance.offline) continue;

			// Get progress
			if (instance['metrics'] !== undefined) {
				progress += parseFloat(instance['metrics']['progress'] || 0.0);
				progressCount += 1;
			}
		}

		// Prepare response
		var metrics = {};

		// Update fields
		metrics['progress'] = (progress / progressCount) || 0;
		metrics['load'] = (this.index['load'] || [])[1] || 0.0;
		metrics['uptime'] = (this.index['uptime'] || [])[0] || 0.0;
		metrics['idletime'] = (this.index['uptime'] || [])[1] || 0.0;
		metrics['runhours'] = this.index['runhours'] || 0;

		// Calculate activity index = CPU load (0% ~ 200%)
		var activity = (this.index['load'] || [])[1] || 0.0;
		if (activity > 1.0) {
			// 1.0 - 2.0 == 80% -- 100%
			if (activity > 2.0) activity = 2.0;
			activity = 0.8 + (activity - 1.0) * 0.2;
		} else {
			// 0.0 - 1.0 == 0% - 80%
			activity *= 0.8;
		}
		metrics['activity'] = activity;

		// Fire callback
		console.log("summarisation:", metrics);
		$(this).triggerHandler('metrics.details', [ metrics ]);

	}

	/**
	 * Update index configuration
	 */
	DQFrontEnd.prototype.__updateInstance = function( instance, metrics ) {

		// If instance was offline, make it online
		if (instance['offline']) {

			// Update instance properties
			instance['metrics'] = metrics;
			instance['offline'] = false;

			// Trigger online event
			$(this).triggerHandler('online.instance', [ instance ]);
			$(this).triggerHandler('metrics.instance', [ metrics, instance, ]);
			return;

		}

		// Check if metrics has changed
		if (!this.__same(instance['metrics'], metrics)) {

			// Update the metrics of an instance
			instance['metrics'] = metrics;

			// Trigger metrics event
			$(this).triggerHandler('metrics.instance', [ metrics, instance, ]);

		}

	}

	/**
	 * Update index configuration
	 */
	DQFrontEnd.prototype.__updateIndex = function( index ) {

		// Update index
		this.index = index;

		// Check for new instances
		var inst = index['instances'] || [];
		for (var i=0; i<inst.length; i++) {
			var ii = inst[i], found = false;

			// Check if the specified instance exists on local instances
			for (var j=0; j<this.instances.length; j++) {
				var ij= this.instances[j];
				if (ii['uuid'] == ij['uuid']) {
					found = true;
					break;
				}
			}

			// If not found, it's new 
			if (!found) {

				// Populate some useful fields
				index['instances'][i]['offline'] = true;
				index['instances'][i]['metrics'] = { };

				// Trigger event
				$(this).triggerHandler('created.instance', [ ii ])
			}

		}

		// Check the other way around: If a previous
		// instance is no longer there
		for (var i=0; i<this.instances.length; i++) {
			var ii = this.instances[i], found = false;

			// Check if the specified instance exists on local instances
			for (var j=0; j<inst.length; j++) {
				var ij= inst[j];
				if (ii['uuid'] == ij['uuid']) {
					found = true;
					break;
				}
			}

			// If not found, it's gone 
			if (!found) {
				// Trigger event
				$(this).triggerHandler('destroyed.instance', [ ii ])
			}

		}

		// Update instances
		this.instances = index['instances'] || [];

	}

	/**
	 * Update machine configuration
	 */
	DQFrontEnd.prototype.__updateMachine = function( machine ) {

		// Update machine configuration
		this.machine = machine;

		// If we were offline before, trigger online event
		if (this.offline) {
			this.offline = false;
			$(this).triggerHandler('online', [ this.machine ]);
		}

	}

	/**
	 * Mark machine as offline
	 */
	DQFrontEnd.prototype.__markOffline = function() {
		if (this.offline) return;
		
		// Take down all instances
		for (var i=0; i<this.instances.length; i++) {
			this.__markOfflineInstance( this.instances[i] );
		}

		// Reset state
		this.instances = [];
		this.index = {};
		this.machine = {};

		// Mark as offline
		this.offline = true;
		// Trigger offline event
		$(this).triggerHandler('offline');
	}

	/**
	 * Internal polling function
	 */
	DQFrontEnd.prototype.__poll = function() {

		// Exit if a poll is currently running
		if (this.pollActive || this.disabled) {
			return;
		}

		// Schedule next poll
		var schedule_next = (function() {
			// Deactivate poll flag
			this.pollActive = false;
			// Schedule next poll
			this.pollTimer = setTimeout( this.__poll.bind(this), 5000 );
			// Update summarisation
			this.__updateSummarization();
		}).bind(this);

		/**
		 * Helper function to chain instance polling
		 */
		var __check_instance = (function(instance, next) {
			$.ajax({
				"url": this.baseUrl + instance['wwwroot'] + '/metrics.json',
				"method": "GET",
				"dataType": "json",
				"data": {
					"s": (this.seq_id++)
				}
			})
			.done((function(metrics) {
				// Update metrics configuration
				this.__updateInstance(instance, metrics);
			}).bind(this))
			.fail((function() {
				// Mark machine as offline
				this.__markOfflineInstance(instance);
			}).bind(this))
			.always((function() {
				// Always call next function in chain
				next();
			}).bind(this));

		}).bind(this);

		/**
		 * Update machine details according to index information.
		 */
		var __check_instances = (function() {

			// Prepare call stack
			var call_stack = [ schedule_next ];

			// Insert calls for every instance
			for (var i=0; i<this.instances.length; i++) {
				// Prepend instance check
				call_stack.unshift((function(inst) {
					return function(next) {
						__check_instance( inst, next );
					};
				})(this.instances[i]));
			}

			// Call function chain
			var run_Chain = function() {
				if (call_stack.length == 1) {
					var fn = call_stack.shift();
					fn();
				} else {
					var fn = call_stack.shift();
					fn(run_Chain);
				}
			};

			// Start calling the chain
			run_Chain();

		}).bind(this);

		/**
		 * Check /index.json for detailed instance information
		 * and online/offline detection.
		 */
		var __check_index = (function() {
			$.ajax({
				"url": this.baseUrl + "/index.json",
				"method": "GET",
				"dataType": "json",
				"data": {
					"s": (this.seq_id++)
				}
			})
			.done((function(index) {
				// Update index configuration
				this.__updateIndex(index);
				// Continue with checking instances
				__check_instances();
			}).bind(this))
			.fail((function() {
				// Mark machine as offline
				this.__markOffline();
				// Schedule next poll
				schedule_next();
			}).bind(this));

		}).bind(this);

		/**
		 * Check /machine.json for general machine
		 * information and online/offline detection.
		 */
		var __check_machine = (function() {
			$.ajax({
				"url": this.baseUrl + "/machine.json",
				"method": "GET",
				"dataType": "json",
				"data": {
					"s": (this.seq_id++)
				}
			})
			.done((function(machine) {
				// Update machine configuration
				this.__updateMachine(machine);
				// Continue with index update
				__check_index();
			}).bind(this))
			.fail((function() {
				// Mark machine as offline
				this.__markOffline();
				// Schedule next poll
				schedule_next();
			}).bind(this));

		}).bind(this);

		// We are running the poll
		this.pollActive = null;

		// If we are offline, start with machine information.
		if (this.offline) {
			__check_machine();
		} else {
			__check_index();		
		}

	}

	/**
	 * Enable and specify base URL
	 */
	DQFrontEnd.prototype.enable = function( baseUrl ) {
		// If already enabled, quit
		if (!this.disabled) return;
		// Keep the front-end base URL
		this.baseUrl = baseUrl;
		// Start polling
		this.disabled = false;
		this.__poll();
	}

	/**
	 * Disable and fire all appropriate clean-up events
	 */
	DQFrontEnd.prototype.disable = function() {
		// If already disabled, quit
		if (this.disabled) return;
		// Mark as disabled (this will stop polling)
		this.disabled = true;
	}

	return DumbQ;

});
