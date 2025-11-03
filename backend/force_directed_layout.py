#!/usr/bin/env python3
"""
Force-directed graph layout algorithm for network map visualization.
Implements a simple spring-force algorithm to position nodes.
"""
import math
import random


def force_directed_layout(nodes, width=1200, height=800, iterations=100, 
                          k=50.0, repulsion_strength=1000.0, attraction_strength=0.01):
    """
    Apply force-directed layout algorithm to position nodes.
    
    Args:
        nodes: List of node dicts with 'x', 'y', and optional 'ip', 'type'
        width: Canvas width
        height: Canvas height
        iterations: Number of iterations to run
        k: Optimal distance between nodes
        repulsion_strength: Strength of repulsion force
        attraction_strength: Strength of attraction force (for connected nodes)
    
    Returns:
        List of nodes with updated x, y positions
    """
    if not nodes:
        return nodes
    
    # Initialize positions if not present
    for node in nodes:
        if 'x' not in node or node.get('x') is None:
            node['x'] = random.uniform(0, width)
        if 'y' not in node or node.get('y') is None:
            node['y'] = random.uniform(0, height)
    
    # Create edges (connect gateway to all other nodes)
    gateway = None
    for node in nodes:
        if node.get('type') == 'gateway':
            gateway = node
            break
    
    edges = []
    if gateway:
        for node in nodes:
            if node['ip'] != gateway['ip']:
                edges.append((gateway, node))
    
    # Run force-directed iterations
    for iteration in range(iterations):
        # Calculate repulsion forces (all nodes repel each other)
        forces = {}
        for node in nodes:
            forces[node['ip']] = {'x': 0.0, 'y': 0.0}
        
        for i, node1 in enumerate(nodes):
            for node2 in nodes[i+1:]:
                dx = node1['x'] - node2['x']
                dy = node1['y'] - node2['y']
                distance = math.sqrt(dx*dx + dy*dy) or 1.0  # Avoid division by zero
                
                # Repulsion force (inversely proportional to distance)
                force = repulsion_strength / (distance * distance)
                fx = (dx / distance) * force
                fy = (dy / distance) * force
                
                forces[node1['ip']]['x'] += fx
                forces[node1['ip']]['y'] += fy
                forces[node2['ip']]['x'] -= fx
                forces[node2['ip']]['y'] -= fy
        
        # Calculate attraction forces (connected nodes attract)
        for node1, node2 in edges:
            dx = node2['x'] - node1['x']
            dy = node2['y'] - node1['y']
            distance = math.sqrt(dx*dx + dy*dy) or 1.0
            
            # Attraction force (proportional to distance)
            force = attraction_strength * (distance - k)
            fx = (dx / distance) * force
            fy = (dy / distance) * force
            
            forces[node1['ip']]['x'] += fx
            forces[node1['ip']]['y'] += fy
            forces[node2['ip']]['x'] -= fx
            forces[node2['ip']]['y'] -= fy
        
        # Apply forces with damping
        damping = 0.9
        for node in nodes:
            node['x'] += forces[node['ip']]['x'] * damping
            node['y'] += forces[node['ip']]['y'] * damping
            
            # Keep nodes within bounds
            node['x'] = max(50, min(width - 50, node['x']))
            node['y'] = max(50, min(height - 50, node['y']))
        
        # Reduce forces over time (cooling)
        repulsion_strength *= 0.95
        attraction_strength *= 0.95
    
    return nodes

