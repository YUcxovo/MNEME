(function () {
    "use strict";

    const palette = ["#78bfd2", "#7bb274", "#d98a86", "#b79ad6", "#e2b478", "#6aa6d8"];
    let selectedId = null;
    let nodeSelection = null;
    let simulation = null;

    function stableHash(value) {
        let hash = 0;
        for (let index = 0; index < value.length; index += 1) {
            hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0;
        }
        return Math.abs(hash);
    }

    function nodeColor(node) {
        const key = node.clusterId || node.category || "uncategorized";
        return palette[stableHash(key) % palette.length];
    }

    function nodeRadius(node, centerId) {
        if (node.id === centerId) {
            return 18;
        }
        const score = Number.isFinite(node.rankScore) ? node.rankScore : 0;
        return 11 + Math.min(5, Math.max(0, score) * 5);
    }

    function shortTitle(title) {
        return title.length > 30 ? title.slice(0, 27) + "..." : title;
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
        d3.select("html").style("height", height + "px");
        d3.select("body").style("height", height + "px");
        host.style("height", height + "px");

        const svg = host.append("svg")
            .attr("width", width)
            .attr("height", height)
            .attr("viewBox", [0, 0, width, height])
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
            .attr("fill", nodeColor);

        nodeSelection.append("text")
            .attr("x", 0)
            .attr("y", function (node) { return nodeRadius(node, payload.centerId) + 17; })
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
                    .distance(105)
                    .strength(0.55)
            )
            .force("charge", d3.forceManyBody().strength(-310))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force(
                "collision",
                d3.forceCollide().radius(function (node) {
                    return nodeRadius(node, payload.centerId) + 24;
                })
            )
            .on("tick", function () {
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
