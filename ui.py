import bpy
from bpy.props import StringProperty, EnumProperty

def find_geometry_node_group(ob):
    for modifier in ob.modifiers:
        if modifier.type == 'NODES':
            return modifier.node_group
    return None

class ModifierLayersPanel(bpy.types.Panel):
    bl_idname = "NODE_LAYERS_PT_modifier_layers"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"
    bl_label = "Node Layers"

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        ob = context.object

        if (node_group := find_geometry_node_group(ob)) is None:
            return

        output_node = None
        for node in node_group.nodes:
            if node.bl_idname == 'NodeGroupOutput':
                output_node = node
                break
        else:
            return


        props = layout.operator("node_layers.add_node_layer")
        props.group_name = node_group.name
        props.next_node_name = output_node.name
        props.next_socket_identifier = output_node.inputs[0].identifier
        active_node = node_group.nodes.active
        if active_node is not None:
            if main_output := find_main_output(active_node):
                for link in main_output.links:
                    props.next_node_name = link.to_node.name
                    props.next_socket_identifier = link.to_socket.identifier
                props.prev_node_name = active_node.name
                props.prev_socket_identifier = main_output.identifier


        final_output_socket = output_node.inputs[0]
        layer_column = layout.column(align=True)
        draw_layer__single_input(layer_column, 0, node_group, final_output_socket)

class ModifierLayerSettingsPanel(bpy.types.Panel):
    bl_idname = "NODE_LAYERS_PT_node_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"
    bl_label = "Settings"

    node_history = []

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        ob = context.object

        if not (node_group := find_geometry_node_group(ob)):
            return

        if not (active_node := node_group.nodes.active):
            return

        active_node_name = active_node.name
        if active_node_name in self.node_history:
            self.node_history.remove(active_node_name)
        self.node_history.insert(0, active_node_name)
        # Limit node history length.
        del self.node_history[5:]

        use_node_history = False
        if use_node_history:
            for node_name in self.node_history:
                if (node := node_group.nodes.get(node_name)) is None:
                    continue
                box = layout.box()
                box.label(text=f"Node: {node_name}")
                draw_node_settings(box, node_group, node, context)
        else:
            draw_node_settings(layout, node_group, active_node, context)


def draw_node_settings(layout, node_group, node, context):
    node.draw_buttons(context, layout)
    for socket in node.inputs:
        if not socket.enabled:
            continue
        row = layout.row()
        socket.draw(context, row, node, socket.name)
        subrow = row.row()
        subrow.enabled = len(socket.links) == 0
        props = row.operator("node_layers.add_node_layer", text="", icon='DECORATE_DRIVER')
        props.group_name = node_group.name
        props.next_node_name = node.name
        props.next_socket_identifier = socket.identifier


class AddNodeLayerOperator(bpy.types.Operator):
    bl_idname = "node_layers.add_node_layer"
    bl_label = "Add Node Layer"
    bl_property = "item"

    item: EnumProperty(items=[
        ("GeometryNodeSubdivisionSurface", "Subdision Surface", ""),
        ("GeometryNodeScaleElements", "Scale Elements", ""),
        ("GeometryNodeSplitEdges", "Split Edges", ""),
        ("GeometryNodeMeshCube", "Cube", ""),
        ("GeometryNodeMeshCylinder", "Cylinder", ""),
        ("GeometryNodeInstanceOnPoints", "Instance on Points", ""),
        ("FunctionNodeRandomValue", "Random Value", ""),
        ("GeometryNodeJoinGeometry", "Join Geometry", ""),
        ("GeometryNodeTransform", "Transform", ""),
    ])

    group_name: StringProperty(options={'SKIP_SAVE'})

    next_node_name: StringProperty(options={'SKIP_SAVE'})
    next_socket_identifier: StringProperty(options={'SKIP_SAVE'})

    prev_node_name: StringProperty(options={'SKIP_SAVE'})
    prev_socket_identifier: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'CANCELLED'}

    def execute(self, context):
        if (node_group := bpy.data.node_groups.get(self.group_name)) is None:
            return {'CANCELLED'}
        if (next_node := node_group.nodes.get(self.next_node_name)) is None:
            return {'CANCELLED'}
        if (next_socket := find_socket_by_identifier(next_node.inputs, self.next_socket_identifier)) is None:
            return {'CANCELLED'}

        if prev_node := node_group.nodes.get(self.prev_node_name):
            prev_socket = find_socket_by_identifier(prev_node.outputs, self.prev_socket_identifier)

        new_node_idname = self.item

        new_node = node_group.nodes.new(new_node_idname)
        new_node.location = next_node.location
        next_node.location.x += 200

        for node in node_group.nodes:
            node.select = False
        node_group.nodes.active = new_node
        new_node.select = True

        if (main_output := find_main_output(new_node)) is None:
            return {'CANCELLED'}

        main_input = find_main_input(new_node, main_output)

        if prev_node is None:
            if not next_socket.is_multi_input:
                old_links = list(next_socket.links)
                assert len(old_links) <= 1
                if len(old_links) == 1:
                    old_link = old_links[0]
                    origin_socket = old_link.from_socket
                    node_group.links.remove(old_link)
                    if main_input is not None:
                        node_group.links.new(main_input, origin_socket)
            node_group.links.new(next_socket, main_output)
        else:
            for link in node_group.links:
                if link.from_socket == prev_socket and link.to_socket == next_socket:
                    node_group.links.remove(link)
                    break
            node_group.links.new(next_socket, main_output)
            if main_input is not None:
                node_group.links.new(main_input, prev_socket)

        return {'FINISHED'}

def find_socket_by_identifier(sockets, identifier):
    for socket in sockets:
        if socket.identifier == identifier:
            return socket
    return None

class RemoveNodeLayerOperator(bpy.types.Operator):
    bl_idname = "node_layers.remove_node_layer"
    bl_label = "Remove Node Layer"
    bl_options = {'UNDO'}

    group_name: StringProperty(options={'SKIP_SAVE'})
    node_name: StringProperty(options={'SKIP_SAVE'})
    output_socket_identifier: StringProperty(options={'SKIP_SAVE'})

    target_node_name: StringProperty(options={'SKIP_SAVE'})
    target_socket_identifier: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if (node_group := bpy.data.node_groups.get(self.group_name)) is None:
            return {'CANCELLED'}
        if (node := node_group.nodes.get(self.node_name)) is None:
            return {'CANCELLED'}
        for socket in node.outputs:
            if socket.identifier == self.output_socket_identifier:
                output_socket = socket
                break
        else:
            return {'CANCELLED'}
        if (target_node := node_group.nodes.get(self.target_node_name)) is None:
            return {'CANCELLED'}
        for socket in target_node.inputs:
            if socket.identifier == self.target_socket_identifier:
                target_socket = socket
                break
        else:
            return {'CANCELLED'}

        for link in node_group.links:
            if link.from_socket == output_socket and link.to_socket == target_socket:
                node_group.links.remove(link)
                break

        main_input = find_main_input(node, output_socket)
        if main_input is not None:
            for link in main_input.links:
                node_group.links.new(target_socket, link.from_socket)

        return {'FINISHED'}

class MakeNodeActiveOperator(bpy.types.Operator):
    bl_idname = "node_layers.make_node_active"
    bl_label = "Make Node Active"

    group_name: StringProperty(options={'SKIP_SAVE'})
    node_name: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if not (node_group := bpy.data.node_groups.get(self.group_name)):
            return {'CANCELLED'}
        if not (newly_active_node := node_group.nodes.get(self.node_name)):
            return {'CANCELLED'}
        for node in node_group.nodes:
            node.select = False
        node_group.nodes.active = newly_active_node
        newly_active_node.select = True
        return {'FINISHED'}

def draw_layer__single_input(layer_column, indentation, node_group, input_socket):
    links = input_socket.links
    if len(links) == 0:
        return

    origin_socket = links[0].from_socket
    draw_layer__output(layer_column, indentation, node_group, origin_socket, input_socket)

def draw_layer__output(layer_column, indentation, node_group, output_socket, target_socket):
    node = output_socket.node
    is_active = node == node_group.nodes.active

    layer_row = layer_column.row()
    add_indentation(layer_row, indentation)

    left_row = layer_row.row()
    left_row.alignment = 'LEFT'
    left_row.prop(node, "mute", text="", icon='CHECKBOX_DEHLT' if node.mute else 'CHECKBOX_HLT', emboss=is_active)
    props = left_row.operator("node_layers.make_node_active", text=node.name, emboss=False)
    props.group_name = node_group.name
    props.node_name = node.name

    right_row = layer_row.row()
    right_row.alignment = 'RIGHT'
    props = right_row.operator("node_layers.remove_node_layer", text="", icon='X', emboss=False)
    props.group_name = node_group.name
    props.node_name = node.name
    props.output_socket_identifier = output_socket.identifier
    props.target_node_name = target_socket.node.name
    props.target_socket_identifier = target_socket.identifier

    if len(node.inputs) == 0:
        return

    main_origin = None
    sub_inputs = []

    main_input = find_main_input(node, output_socket)
    if main_input is not None:
        main_input_links = main_input.links
        if len(main_input_links) > 0:
            if main_input.is_multi_input:
                # Might not actually the first link. The sorting info is not exposed yet.
                main_origin = main_input_links[0].from_socket
                for i, link in enumerate(main_input_links[1:], start=1):
                    sub_inputs.append((f"Join {i}", main_input, link.from_socket))
            else:
                main_origin = main_input_links[0].from_socket

    for input_socket in node.inputs:
        if input_socket == main_input:
            continue
        if not input_socket.enabled:
            continue
        input_links = input_socket.links
        if len(input_links) == 0:
            continue
        sub_inputs.append((input_socket.name, input_socket, input_links[0].from_socket))

    sub_indentation = indentation + 1
    for name, input_socket, origin_socket in sub_inputs:
        row = layer_column.row()
        add_indentation(row, sub_indentation)
        row.label(text=f"{name}:")
        draw_layer__output(layer_column, sub_indentation, node_group, origin_socket, input_socket)

    if main_origin is not None:
        draw_layer__output(layer_column, indentation, node_group, main_origin, main_input)

def is_geometry_socket(socket):
    return socket.bl_idname == 'NodeSocketGeometry'

def find_main_output(node):
    for socket in node.outputs:
        if socket.enabled:
            return socket
    return None

def find_main_input(node, output_socket):
    output_is_geometry = is_geometry_socket(output_socket)
    for input_socket in node.inputs:
        if output_is_geometry and not is_geometry_socket(input_socket):
            continue
        if input_socket.enabled:
            return input_socket
    return None


def add_indentation(row, indentation):
    subrow = row.row(align=True)
    subrow.scale_x = 0.0001 if indentation == 0 else 0.6
    for _ in range(max(1, indentation)):
        # subrow.label(icon='X')
        subrow.label(icon='BLANK1')
