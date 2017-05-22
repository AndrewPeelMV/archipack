# -*- coding:utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110- 1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# ----------------------------------------------------------
# Author: Stephen Leger (s-leger)
# Inspired by Okavango's np_point_move
# ----------------------------------------------------------
"""
    Usage:
        from .archipack_snap import snap_point

        snap_point(takeloc, draw_callback, action_callback, constraint_axis)

        arguments:

        takeloc Vector3d location of point to snap

        constraint_axis boolean tuple for each axis
              eg: (True, True, False) to constrtaint to xy plane

        draw_callback(context, sp)
            sp.takeloc
            sp.placeloc
            sp.delta

        action_callback(context, event, state, sp)
            state in {'SUCCESS', 'CANCEL'}
            sp.takeloc
            sp.placeloc
            sp.delta

        with 3d Vectors
        - delta     = placeloc - takeloc
        - takeloc
        - placeloc


        NOTE:
            may change grid size to 0.1 round feature (SHIFT)
            see https://blenderartists.org/forum/showthread.php?205158-Blender-2-5-Snap-mode-increment
            then use a SHIFT use grid snap

"""

import bpy
from bpy.types import Operator
from mathutils import Vector, Matrix


def dumb_callback(context, event, state, sp):
    return


def dumb_draw(sp, context, event):
    return


class SnapStore:
    """
        Global store
    """
    callback = None
    draw = None
    helper = None
    takeloc = Vector((0, 0, 0))
    placeloc = Vector((0, 0, 0))
    constraint_axis = (True, True, False)
    helper_matrix = Matrix()
    transform_orientation = 'GLOBAL'


def snap_point(takeloc=None,
                draw=dumb_draw,
                callback=dumb_callback,
                takemat=None,
                constraint_axis=(True, True, False),
                transform_orientation='GLOBAL',
                mode='OBJECT'):
    """
        Invoke op from outside world
        in a convenient importable function

        transform_orientation in [‘GLOBAL’, ‘LOCAL’, ‘NORMAL’, ‘GIMBAL’, ‘VIEW’]

        draw(sp, context) a draw callback
        callback(context, event, state, sp) action callback

        Use either :
        takeloc Vector, unconstraint or system axis constraints
        takemat Matrix, constaint to this matrix as 'LOCAL' coordsys
            The snap source helper use it as world matrix
            so it is possible to constraint to user defined coordsys.
    """
    SnapStore.draw = draw
    SnapStore.callback = callback
    SnapStore.constraint_axis = constraint_axis

    if takemat is not None:
        SnapStore.helper_matrix = takemat
        takeloc = takemat.translation
        transform_orientation = 'LOCAL'
    else:
        if takeloc is None:
            raise ValueError("ArchipackSnap: Either takeloc or takemat must be defined")
        SnapStore.helper_matrix = Matrix().Translation(takeloc)

    SnapStore.takeloc = takeloc
    SnapStore.placeloc = takeloc
    SnapStore.transform_orientation = transform_orientation

    # @NOTE: unused mode var to switch between OBJECT and EDIT mode
    # for ArchipackSnapBase to be able to handle both modes
    # must implements corresponding helper create and delete actions
    SnapStore.mode = mode
    bpy.ops.archipack.snap('INVOKE_DEFAULT')


class ArchipackSnapBase():
    """
        Helper class for snap Operators
        store and restore context
        create and destroy helper
        install and remove a draw_callback working while snapping

        store and provide access to 3d Vectors
        in draw_callback and action_callback
        - delta     = placeloc - takeloc
        - takeloc
        - placeloc
    """
    def __init__(self):
        self.act = None
        self.sel = []
        self.use_snap = False
        self.snap_element = None
        self.snap_target = None
        self.pivot_point = None
        self.transform_orientation = None
        self._draw_handler = None

    def init(self, context, event):
        # Store context data
        self.sel = [o for o in context.selected_objects]
        self.act = context.active_object
        bpy.ops.object.select_all(action="DESELECT")
        self.use_snap = context.tool_settings.use_snap
        self.snap_element = context.tool_settings.snap_element
        self.snap_target = context.tool_settings.snap_target
        self.pivot_point = context.space_data.pivot_point
        self.transform_orientation = context.space_data.transform_orientation
        self.create_helper(context)
        self.set_transform_orientation(context)
        args = (self, context)
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(SnapStore.draw, args, 'WINDOW', 'POST_PIXEL')

    def exit(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')
        self.destroy_helper(context)
        # Restore original context
        context.tool_settings.use_snap = self.use_snap
        context.tool_settings.snap_element = self.snap_element
        context.tool_settings.snap_target = self.snap_target
        context.space_data.pivot_point = self.pivot_point
        context.space_data.transform_orientation = self.transform_orientation
        for o in self.sel:
            o.select = True
        if self.act is not None:
            context.scene.objects.active = self.act

    def set_transform_orientation(self, context):
        """
            Allow local constraint orientation to be set
        """
        context.space_data.transform_orientation = SnapStore.transform_orientation

    def create_helper(self, context):
        """
            Create a helper with fake user
            or find older one in bpy data and relink to scene
            currently only support OBJECT mode

            Do target helper be linked to scene in order to work ?

        """
        helper_idx = bpy.data.objects.find('Archipack_snap_helper')
        if helper_idx > -1:
            helper = bpy.data.objects[helper_idx]
            if context.scene.objects.find('Archipack_snap_helper') < 0:
                context.scene.objects.link(helper)
        else:
            bpy.ops.object.add(type='MESH')
            helper = context.active_object
            helper.name = 'Archipack_snap_helper'
            helper.use_fake_user = True
            helper.data.use_fake_user = True
        # hide snap helper
        # helper.hide = True
        helper.matrix_world = SnapStore.helper_matrix
        helper.select = True
        context.scene.objects.active = helper
        SnapStore.helper = helper

    def destroy_helper(self, context):
        """
            Unlink helper
            currently only support OBJECT mode
        """
        if SnapStore.helper is not None:
            context.scene.objects.unlink(SnapStore.helper)
            SnapStore.helper = None

    @property
    def delta(self):
        return self.placeloc - self.takeloc

    @property
    def takeloc(self):
        return SnapStore.takeloc

    @property
    def placeloc(self):
        # take from helper when there so the delta
        # is working even while modal is running
        if SnapStore.helper is not None:
            return SnapStore.helper.location
        else:
            return SnapStore.placeloc


class ARCHIPACK_OT_snap(ArchipackSnapBase, Operator):
    bl_idname = 'archipack.snap'
    bl_label = 'Archipack snap'
    bl_options = {'UNDO'}

    def modal(self, context, event):
        context.area.tag_redraw()
        # NOTE: this part only run after transform LEFTMOUSE RELEASE
        # or with ESC and RIGHTMOUSE
        if event.type in ('ESC', 'RIGHTMOUSE'):
            SnapStore.callback(context, event, 'CANCEL', self)
        else:
            SnapStore.placeloc = SnapStore.helper.location
            SnapStore.callback(context, event, 'SUCCESS', self)
        self.exit(context)
        return{'FINISHED'}

    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.init(context, event)
            context.window_manager.modal_handler_add(self)
            bpy.ops.transform.translate('INVOKE_DEFAULT',
                constraint_axis=SnapStore.constraint_axis,
                constraint_orientation=SnapStore.transform_orientation,
                release_confirm=True)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'FINISHED'}


def register():
    bpy.utils.register_class(ARCHIPACK_OT_snap)


def unregister():
    bpy.utils.unregister_class(ARCHIPACK_OT_snap)
