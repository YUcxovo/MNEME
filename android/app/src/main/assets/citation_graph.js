(function () {
    "use strict";

    const palette = ["#78bfd2", "#7bb274", "#d98a86", "#b79ad6", "#e2b478", "#6aa6d8"];
    let selectedId = null;
    let nodeSelection = null;
    let simulation = null;

    function nodeColorKey(node) {
        return node.clusterId || node.category || "uncategorized";
    }

    function graphColorMap(nodes) {
        const keys = Array.from(new Set(nodes.map(nodeColorKey))).sort();
        return new Map(keys.map(function (key, index) {
            return [key, palette[index % palette.length]];
        }));
    }

    function nodeRadius(node, centerId) {
        if (node.id === centerId) {
            return 18;
        }
        const score = Number.isFinite(node.rankScore) ? node.rankScore : 0;
        return 11 + Math.min(5, Math.max(0, score) * 5);
    }

    function shortTitle(title) {
        return title.length > 18 ? title.slice(0, 15) + "..." : title;
    }

    function notifySelection(id) {
        if (window.MnemeGraphBridge && typeof window.MnemeGraphBridge.selectNode === "function") {
            window.MnemeGraphBridge.selectNode(id);
        }
    }

    function selectNodeById(id, notify) {
        if (!nodeSelection || !nodeSelection.data().some(function (node) { return node.id === id; })) {
            return false;
        }
        selectedId = id;
        nodeSelection.classed("selected", function (node) { return node.id === selectedId; });
        if (notify !== false) {
            notifySelection(id);
        }
        return true;
    }

    function render(payload) {
        const host = d3.select("#graph");
        host.selectAll("*").remove();
        if (simulation) {
            simulation.stop();
        }

        const width = Math.max(320, document.documentElement.clientWidth || 320);
        const height = Math.max(360, document.documentElement.clientHeight || 360);
        const nodes = payload.nodes.map(function (node) { return Object.assign({}, node); });
        const edges = payload.edges.map(function (edge) { return Object.assign({}, edge); });
        const colorMap = graphColorMap(nodes);
        const clusterKeys = Array.from(colorMap.keys());
        const clusterIndex = new Map(clusterKeys.map(function (key, index) { return [key, index]; }));
        const linkDistance = Math.max(76, Math.min(96, width / 4));
        const chargeStrength = -Math.max(130, Math.min(260, 2400 / Math.max(nodes.length, 1)));
        const horizontalPadding = Math.min(64, width / 5);

        function clusterAngle(node) {
            const index = clusterIndex.get(nodeColorKey(node)) || 0;
            return (2 * Math.PI * index / Math.max(clusterKeys.length, 1)) - (Math.PI / 2);
        }

        function clusterX(node) {
            return node.id === payload.centerId
                ? width / 2
                : width / 2 + Math.cos(clusterAngle(node)) * width * 0.22;
        }

        function clusterY(node) {
            return node.id === payload.centerId
                ? height / 2
                : height / 2 + Math.sin(clusterAngle(node)) * height * 0.2;
        }
        d3.select("html").style("height", height + "px");
        d3.select("body").style("height", height + "px");
        host.style("height", height + "px");

        const svg = host.append("svg")
            .attr("width", width)
            .attr("height", height)
            .attr("viewBox", [0, 0, width, height])
            .classed("dense", nodes.length > 20)
            .attr("role", "img")
            .attr("aria-label", "Directed paper citation graph");

        const definitions = svg.append("defs");
        definitions.append("marker")
            .attr("id", "citation-arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 24)
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("fill", "#8a98ad")
            .attr("d", "M0,-5L10,0L0,5");

        const viewport = svg.append("g");
        svg.call(
            d3.zoom()
                .scaleExtent([0.45, 4])
                .on("zoom", function (event) { viewport.attr("transform", event.transform); })
        );

        const linkSelection = viewport.append("g")
            .selectAll("line")
            .data(edges)
            .join("line")
            .attr("class", "edge")
            .attr("stroke-width", function (edge) {
                return 1.2 + Math.min(2.8, Math.max(0, edge.weight || 0) * 2.8);
            })
            .attr("marker-end", "url(#citation-arrow)");

        nodeSelection = viewport.append("g")
            .selectAll("g")
            .data(nodes, function (node) { return node.id; })
            .join("g")
            .attr("class", function (node) {
                return "node" + (node.id === payload.centerId ? " center" : "");
            })
            .attr("role", "button")
            .attr("tabindex", 0)
            .attr("aria-label", function (node) { return "Select paper: " + node.title; })
            .attr("data-node-id", function (node) { return node.id; })
            .on("click", function (event, node) {
                event.stopPropagation();
                selectNodeById(node.id, true);
            })
            .on("keydown", function (event, node) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectNodeById(node.id, true);
                }
            })
            .call(
                d3.drag()
                    .on("start", function (event, node) {
                        if (!event.active) {
                            simulation.alphaTarget(0.25).restart();
                        }
                        node.fx = node.x;
                        node.fy = node.y;
                    })
                    .on("drag", function (event, node) {
                        node.fx = event.x;
                        node.fy = event.y;
                    })
                    .on("end", function (event, node) {
                        if (!event.active) {
                            simulation.alphaTarget(0);
                        }
                        node.fx = null;
                        node.fy = null;
                    })
            );

        nodeSelection.append("circle")
            .attr("r", function (node) { return nodeRadius(node, payload.centerId); })
            .attr("fill", function (node) { return colorMap.get(nodeColorKey(node)); });

        nodeSelection.append("text")
            .attr("x", 0)
            .attr("y", function (node) { return nodeRadius(node, payload.centerId) + 14; })
            .attr("text-anchor", "middle")
            .text(function (node) { return shortTitle(node.title); });

        nodeSelection.append("title")
            .text(function (node) {
                const category = node.category ? " - " + node.category : "";
                return node.title + category;
            });

        simulation = d3.forceSimulation(nodes)
            .force(
                "link",
                d3.forceLink(edges)
                    .id(function (node) { return node.id; })
                    .distance(linkDistance)
                    .strength(0.55)
            )
            .force("charge", d3.forceManyBody().strength(chargeStrength))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("cluster-x", d3.forceX(clusterX).strength(0.08))
            .force("cluster-y", d3.forceY(clusterY).strength(0.08))
            .force(
                "collision",
                d3.forceCollide().radius(function (node) {
                    return nodeRadius(node, payload.centerId) + 20;
                })
            )
            .on("tick", function () {
                nodes.forEach(function (node) {
                    const radius = nodeRadius(node, payload.centerId);
                    node.x = Math.max(horizontalPadding, Math.min(width - horizontalPadding, node.x));
                    node.y = Math.max(radius + 8, Math.min(height - radius - 32, node.y));
                });
                linkSelection
                    .attr("x1", function (edge) { return edge.source.x; })
                    .attr("y1", function (edge) { return edge.source.y; })
                    .attr("x2", function (edge) { return edge.target.x; })
                    .attr("y2", function (edge) { return edge.target.y; });
                nodeSelection.attr(
                    "transform",
                    function (node) { return "translate(" + node.x + "," + node.y + ")"; }
                );
            });

        selectedId = nodes.some(function (node) { return node.id === selectedId; })
            ? selectedId
            : payload.centerId;
        selectNodeById(selectedId, false);
        document.body.dataset.rendererReady = "true";
    }

    window.MnemeGraph = {
        render: render,
        selectNodeById: function (id) { return selectNodeById(id, true); },
        selectedNodeId: function () { return selectedId; }
    };
}());
