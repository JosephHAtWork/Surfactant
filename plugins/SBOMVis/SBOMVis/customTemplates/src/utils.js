/**
 * Sets the nodes with the given array of IDs with `color` or it's default color if left undefined
 * @param {Array} nodeIDs
 * @param {(String|undefined)} color
 */
export function setNodeColors(nodeIDs, color) {
	nodes.update(
		nodes.get(nodeIDs).map((n) => ({
			id: n.id,
			color: color !== undefined ? color : n.originalColor,
		})),
	);
}

/**
 * Sets CSS color scheme, dark/light mode toggle icon, and updates node font colors
 * @param {String} mode (dark, light, auto)
 */
export function setColorScheme(mode) {
	const toggle = document.getElementById("themeToggle");
	const icon = toggle.querySelector("i");

	const html = document.querySelector("html");

	// Update icon and CSS color-scheme
	const colorSchemes = {
		dark: {
			icon: "fa-solid fa-sun",
			tooltip: "Toggle light mode",
			CSSColorScheme: "dark",
		},
		light: {
			icon: "fa-solid fa-moon",
			tooltip: "Toggle dark mode",
			CSSColorScheme: "light",
		},
	};

	let preferredColorScheme = mode;
	if (mode === "auto") {
		preferredColorScheme = window.matchMedia("(prefers-color-scheme: dark)")
			.matches
			? "dark"
			: "light"; // Use system preferred color
		html.style.setProperty("color-scheme", "light dark");
	} else html.style.setProperty("color-scheme", mode);

	const { icon: iconClass, tooltip } = colorSchemes[preferredColorScheme];
	icon.classList = iconClass;
	toggle.setAttribute("title", tooltip);

	// Update node font colors
	const styles = getComputedStyle(document.body);

	const newIconColor = styles.getPropertyValue(
		preferredColorScheme === "dark" ? "--darkNodeColor" : "--lightNodeColor",
	);
	const newLabelColor = styles.getPropertyValue(
		preferredColorScheme === "dark" ? "--darkTextColor" : "--lightTextColor",
	);

	nodes.update(
		nodes.get().map((n) => ({
			id: n.id,
			icon: { ...n.icon, color: newIconColor },
			font: { ...n.font, color: newLabelColor },
		})),
	);
}

/**
 * Groups nodes together by parent directory or SBOM
 * @param {Array} nodeIDs - Array of node IDs
 * @param {String} group - Either "directory" or "SBOM"
 */
export function groupGraph(group) {
	const ns = nodes.get();

	switch (group) {
		case "directory": {
			nodes.update(
				nodes.get().map((n) => {
					const nodeInstallPath = n.surfactantSoftwareStruct.installPath[0];
					let parentDirectory = nodeInstallPath.substring(
						0,
						nodeInstallPath.lastIndexOf("/"),
					);

					if (n.surfactantSoftwareStruct.installPath.length > 1)
						// If a entry has multiple install paths (eg multiple empty files), create a new group for it
						parentDirectory = "<Multiple install paths>";

					return {
						id: n.id,
						group: parentDirectory,
					};
				}),
			);
			break;
		}

		case "SBOM": {
			nodes.update(
				nodes.get().map((n) => ({
					id: n.id,
					group: n?.nodeMetadata?.SBOMFileName,
				})),
			);

			break;
		}
	}
}
