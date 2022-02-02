from json.tool import main
import bpy
from bpy.props import *

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

        if not (node_group := find_geometry_node_group(ob)):
            return

        output_node = None
        for node in node_group.nodes:
            if node.bl_idname == 'NodeGroupOutput':
                output_node = node
                break
        else:
            return

        final_output_socket = output_node.inputs[0]
        draw_layers_for_single_input(layout, node_group, final_output_socket)

class ModifierLayerSettingsPanel(bpy.types.Panel):
    bl_idname = "NODE_LAYERS_PT_node_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"
    bl_label = "Settings"

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

        active_node.draw_buttons(context, layout)
        for socket in active_node.inputs:
            socket.draw(context, layout, active_node, socket.name)

class MakeNodeActiveOperator(bpy.types.Operator):
    bl_idname = "node_layers.make_node_active"
    bl_label = "Make Node Active"

    group_name: StringProperty()
    node_name: StringProperty()

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


def draw_layers_for_single_input(layout, node_group, input_socket):
    links = input_socket.links
    if len(links) == 0:
        return

    origin_socket = links[0].from_socket
    draw_layers_for_output(layout, node_group, origin_socket)


def draw_layers_for_output(layout, node_group, output_socket):
    node = output_socket.node
    is_active = node == node_group.nodes.active

    main_row = layout.row()
    name_row = main_row.row(align=False)
    name_row.alignment = 'LEFT'
    name_row.prop(node, "mute", text="", icon='CHECKBOX_DEHLT' if node.mute else 'CHECKBOX_HLT', emboss=is_active)
    props = name_row.operator("node_layers.make_node_active", text=node.name, emboss=False)
    props.group_name = node_group.name
    props.node_name = node.name

    if len(node.inputs) == 0:
        return

    main_input = node.inputs[0]
    if main_input.bl_idname != 'NodeSocketGeometry':
        return

    if not main_input.is_multi_input:
        draw_layers_for_single_input(layout, node_group, main_input)
        return

    row = layout.row(align=True)
    row.label(text="", icon='BLANK1')
    draw_layers_for_multi_input(row, node_group, main_input)


def draw_layers_for_multi_input(layout, node_group, input_socket):
    col = layout.column()
    links = input_socket.links
    for link in links:
        origin_socket = link.from_socket
        draw_layers_for_output(col, node_group, origin_socket)
        if link != links[-1]:
            subcol = col.column(align=True)
            subcol.scale_y = 0.4
            subcol.separator()
