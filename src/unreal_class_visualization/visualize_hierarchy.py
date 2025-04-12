import json
import os
import networkx as nx
from pyvis.network import Network
import webbrowser
import argparse
from pathlib import Path
from typing import Dict, Optional, Any, Set

# 定义更具体的类型别名
UnrealClassData = Dict[str, Dict[str, Any]]
def parse_unreal_json(json_path: Path) -> Optional[UnrealClassData]:
    """
    Reads and parses the Unreal Engine class information from a JSON file.

    Args:
        json_path (Path): Path object pointing to the JSON file.

    Returns:
        Optional[UnrealClassData]: Parsed data as a dictionary, or None on error.
    """
    if not json_path.is_file():
        print(f"Error: JSON file not found at {json_path}")
        return None
    try:
        with json_path.open('r', encoding='utf-8') as f:
            data: UnrealClassData = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {json_path}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading {json_path}: {e}")
        return None

def build_hierarchy_graph(data: UnrealClassData) -> Optional[nx.DiGraph]:
    """
    Builds a directed graph based on parent-child relationships.

    Args:
        data (UnrealClassData): The dictionary containing Unreal class information.

    Returns:
        Optional[nx.DiGraph]: The constructed graph, or None if data is invalid.
    """
    if not data:
        print("No data provided to build graph.")
        return None

    G = nx.DiGraph()
    all_class_names: Set[str] = set(data.keys())

    # Add all classes as nodes first
    for class_name in all_class_names:
        G.add_node(class_name, title=class_name) # Add title for hover info

    # Add edges based on parent relationship
    for class_name, class_info in data.items():
        parent: Optional[str] = class_info.get('parent')
        # Add edge only if parent exists and is part of our dataset
        if parent and parent in all_class_names:
            # Add edge from parent to child
            G.add_edge(parent, class_name)
        # elif parent:
            # Decide if external parents should be added.
            # Currently, we only link known classes within the dataset.
            # If needed, uncomment below:
            # if parent not in G:
            #     G.add_node(parent, title=f"{parent} (External)", color='grey') # Mark external parents
            # G.add_edge(parent, class_name)
            # print(f"Info: Parent '{parent}' for class '{class_name}' not found in dataset. Linking skipped.")

    return G

def visualize_interactive_graph(graph: nx.DiGraph, output_path: Path) -> None:
    """
    Visualizes the graph interactively using pyvis and saves it as an HTML file.

    Args:
        graph (nx.DiGraph): The graph to visualize.
        output_path (Path): The Path object for the output HTML file.
    """
    if not graph or graph.number_of_nodes() == 0:
        print("Graph is empty, nothing to visualize.")
        return

    # Create a pyvis network instance
    # Adjust height and width as needed
    net = Network(notebook=False, height='95vh', width='100%', directed=True, bgcolor='#222222', font_color='white')

    # Configure physics options for better layout and interaction
    # Experiment with these settings for desired behavior
    net.set_options("""
    var options = {
      "nodes": {
        "font": {
          "size": 12
        },
        "shape": "dot",
        "size": 15
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.5
          }
        },
        "color": {
          "inherit": true
        },
        "smooth": {
          "type": "continuous"
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 200,
        "navigationButtons": true,
        "keyboard": true
      },
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -8000,
          "springConstant": 0.04,
          "springLength": 150
        },
        "minVelocity": 0.75,
        "solver": "barnesHut"
      }
    }
    """)


    # Add nodes and edges from the networkx graph
    # Pyvis automatically uses the 'title' attribute for hover tooltips
    net.from_nx(graph)

    try:
        # Save the graph to an HTML file
        net.save_graph(str(output_path)) # save_graph expects a string path
        print(f"Interactive graph saved to {output_path}")

        # Optionally, try to open the generated HTML file in the default browser
        try:
            # Use Path.as_uri() for better cross-platform compatibility
            webbrowser.open(output_path.as_uri())
            print(f"Attempting to open {output_path} in your browser.")
        except Exception as e:
            print(f"Could not automatically open the file in browser: {e}")
            print(f"Please open '{output_path}' manually in your web browser.")

    except Exception as e:
        print(f"Error saving or opening interactive graph: {e}")


if __name__ == "__main__":
    # Default paths relative to the script location
    script_dir = Path(__file__).parent.resolve()
    default_json_path = script_dir / 'data' / 'unreal.json'
    default_output_html_path = script_dir / 'unreal_class_hierarchy.html'

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Visualize Unreal Engine class hierarchy from JSON data.")
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=default_json_path,
        help=f"Path to the input JSON file (default: {default_json_path})"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=default_output_html_path,
        help=f"Path to save the output HTML file (default: {default_output_html_path})"
    )
    args = parser.parse_args()

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # --- Main execution flow ---
    print(f"Loading data from: {args.input}")
    unreal_data = parse_unreal_json(args.input)

    if unreal_data:
        print("Building hierarchy graph...")
        hierarchy_graph = build_hierarchy_graph(unreal_data)
        if hierarchy_graph:
            print(f"Visualizing graph and saving to: {args.output}")
            visualize_interactive_graph(hierarchy_graph, args.output)
            print("Visualization complete.")
        else:
            print("Failed to build hierarchy graph.")
    else:
        print("Failed to parse JSON data. Exiting.")