$(function() {

	// What's the URL we are running at
	var url = String(window.location);
	if (url.indexOf(".html") != -1) {
		var parts = url.split("/"); parts.pop();
		url = parts.join("/");
	}

	// Trim hash
	if (url.indexOf("#"))
		url = url.split("#")[0];

	// Trim trailing slash
	if (url.substr(url.length-1) == "/")
		url = url.substr(0, url.length-1);

	// Instantiate a new DumbQ Front-End monitor
	var dqfe = new DumbQ.Frontend();

	// Reset UI
	$(".iframe-host").hide();

	// Quick hack to get an incremental cpu ID for every project
	var cpu_map = { };
	function reserve_cpu( id ) {
		var num = 0;
		// Get biggest CPU number
		for (var k in cpu_map) {
			if (cpu_map[k] > num)
				num = cpu_map[k];
		}
		// Get next
		cpu_map[k] = ++num;
		return num;
	}
	function free_cpu( id ) {
		delete cpu_map[id];
	}

	// Bind 'created' listener
	$(dqfe).on('online_instance', function(event, instance, metrics) {
		var iid = instance['uuid'];

		// Delete possible previous nav label
		$('.navbar-projects-dynamic > li.btn-' + iid).remove();

		// Create new element
		var elm = $('<a></a>').appendTo($('<li></li>').appendTo(".navbar-projects-dynamic"))
			.attr("class", "btn-" + iid)
			.attr("href", url + instance['wwwroot'])
			.attr("target", "contentFrame")
			.text("CPU" + reserve_cpu(iid) + " (" + instance['project'] + ')')
			.click(function(e) {
				// Block event
				// Switch to iframe host
				$('.welcome-host').hide();
				$('.iframe-host').show();
				// // Focus to URL (This now uses the standard <a target="..">/<iframe name="..">)
				// $(".iframe-host > iframe").attr("src", url + instance['wwwroot'])
				// Focus on element
				$('.navbar-projects-dynamic > li').removeClass('active');
				$(this).parent().addClass('active');
			});

		// If that's the first, also focus
		if ($('.navbar-projects-dynamic > li').length == 2) {
			elm.click();
		}

	});

	// Bind 'destroyed' listener
	$(dqfe).on('offline_instance', function(event, instance, metrics) {
		var iid = instance['uuid'];
		var elm = $('.navbar-projects-dynamic > li.btn-' + iid);
		if (elm.length == 0) return;

		// Delete
		elm.remove();
		free_cpu(iid);

		// Focus on another tab
		var around = $('.navbar-projects-dynamic > li');
		if (around.length == 1) {
			$(around[0]).click(); // Don't prefer clicking on the home page
		} else {
			$(around[1]).click(); // But DO prefer to click on any other VM
		}

	});

	// Activate front-end
	dqfe.enable( url )

	// Bind 'welcome' button listener
	$('li.btn-welcome').click(function() {
		// Switch to welcome host
		$('.welcome-host').show();
		$('.iframe-host').hide();
		// Focus on element
		$('.navbar-projects-dynamic > li').removeClass('active');
		$(this).addClass('active');
	});


})