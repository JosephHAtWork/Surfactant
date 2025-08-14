const defaultState = {
    isSearchNodeHighlighted: false,
    searchSidebarPanel: null,
    nodeSidebarPanel: null,
    graphOverviewSidebarPanel: null,
    selectedSidebar: ""
};

export const store = {
	state: defaultState,
	listeners: {},

	set(k, v) {
		this.state[k] = v;
		if (this.listeners[k]) {
			for (const callback of this.listeners[k]) {
				callback(v);
			}
		}
	},

	get(k) {
		return this.state[k];
	},

	subscribe(key, callback) {
		if (!this.listeners[key]) {
			this.listeners[key] = [];
		}
		this.listeners[key].push(callback);
	},
};
