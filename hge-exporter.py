import bpy
import sys
import ctypes
# Types
TYPE_BOOLEAN = ctypes.c_int8
TYPE_TERRAIN_ASPECT = ctypes.c_int16
TYPE_TERRAIN_VBO_COMPONENTS_COUNT = ctypes.c_int8
TYPE_ID = ctypes.c_int32
TYPE_OBJECT_TYPE_ID = ctypes.c_int16
TYPE_INSTRUCTION = ctypes.c_int16
TYPE_OBJECT_SIZE = ctypes.c_int32
TYPE_VERTEX_ELEMENT = ctypes.c_float
TYPE_INDEX_ELEMENT = ctypes.c_int32
TYPE_VERTEX_ELEMENT_COUNT = ctypes.c_int32
TYPE_INDICES_COUNT = ctypes.c_int32
TYPE_STRING_LENGTH = ctypes.c_int16
TYPE_CHARACTER = ctypes.c_char
# Constants
OBJECT_TYPE_ID_TERRAIN = TYPE_OBJECT_TYPE_ID(0)
OBJECT_TYPE_ID_GEOMETRY = TYPE_OBJECT_TYPE_ID(1)
OBJECT_TYPE_ID_SKY_BOX = TYPE_OBJECT_TYPE_ID(2)
OBJECT_TYPE_ID_ARMATURE = TYPE_OBJECT_TYPE_ID(3)
BOOLEAN_TRUE = TYPE_BOOLEAN(1)
BOOLEAN_FALSE = TYPE_BOOLEAN(0)
# Prefixes
PREFIX_OCCLUSION_TEST = 'OcclusionTest'
PREFIX_SKELETON = 'Skeleton'  # This mean it does not have scale channel
PREFIX_SKIN = 'Skin'
# Object type
OBJECT_TYPE_STRING_ARMATURE = 'ARMATURE'
OBJECT_TYPE_STRING_MESH = 'MESH'


imported_objects = set()


def save_string(save_file, string):
    save_file.write(TYPE_STRING_LENGTH(len(string)))
    for c in string:
        save_file.write(TYPE_CHARACTER(ord(c)))


def prefix_check(name, prefix) -> bool:
    return name[0:len(prefix)] == prefix


def postfix_check(name, postfix) ->bool:
    return name[len(name)-len(postfix):] == postfix


class HgeVertex():

    class UnKnownVertexTypeError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    class WrappedVertexTypeError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    class VertexGroupOutOfRangeTypeError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def __init__(self, vertex_index, loop_index, vertex_obj, world_matrix, mesh_type, mesh):
        self.mesh = mesh
        if HgeMesh.MESH_TYPE_OCCLUSION == mesh_type:
            self.position = world_matrix * vertex_obj.data.vertices[vertex_index].co
            self.normal = world_matrix * vertex_obj.data.vertices[vertex_index].normal
            self.data = (self.position[0], self.position[1], self.position[2])
        elif HgeMesh.MESH_TYPE_STATIC == mesh_type:
            self.position = world_matrix * vertex_obj.data.vertices[vertex_index].co
            self.normal = world_matrix * vertex_obj.data.vertices[vertex_index].normal
            if vertex_obj.data.uv_layers.active is not None:
                uv = vertex_obj.data.uv_layers.active.data[loop_index].uv
                self.data = (self.position[0], self.position[1], self.position[2],
                             self.normal[0], self.normal[1], self.normal[2], uv[0], uv[1])
            else:
                raise self.WrappedVertexTypeError("Your mesh does not unwrapped yet.")
        elif HgeMesh.MESH_TYPE_SKIN == mesh_type:
            self.position = vertex_obj.data.vertices[vertex_index].co
            self.normal = vertex_obj.data.vertices[vertex_index].normal
            if vertex_obj.data.uv_layers.active is not None:
                self.uv = vertex_obj.data.uv_layers.active.data[loop_index].uv
            else:
                raise self.WrappedVertexTypeError("Your mesh does not unwrapped yet.")
            self.weight = [0.0] * len(vertex_obj.vertex_groups)
            number_of_affect_bones = 0
            for g in vertex_obj.data.vertices[vertex_index].groups:
                index = g.group
                if index < len(vertex_obj.vertex_groups):
                    if g.weight > 0.0:
                        self.weight[index] = g.weight
                        number_of_affect_bones += 1
                else:
                    raise self.VertexGroupOutOfRangeTypeError("Out of range vertex group index.")
            if number_of_affect_bones > mesh.max_number_of_affecting_bone_on_a_vertex:
                mesh.max_number_of_affecting_bone_on_a_vertex = number_of_affect_bones
            self.data = [self.position[0], self.position[1], self.position[2],
                         self.normal[0], self.normal[1], self.normal[2],
                         self.uv[0], self.uv[1]]
        else:
            raise self.UnKnownVertexTypeError("Unknown vertex type")

    def create_data(self):
        bone_index_index = len(self.data)
        self.data += [0.0] * 2 * self.mesh.max_number_of_affecting_bone_on_a_vertex
        bone_weight_index = bone_index_index + self.mesh.max_number_of_affecting_bone_on_a_vertex
        for i, w in enumerate(self.weight):
            if w > 0.0:
                self.data[bone_index_index] = float(i)
                self.data[bone_weight_index] = w
        self.data = tuple(self.data)

    def __str__(self):
        return str(self.data)


class HgeTriangle():

    class UntriangulatedMeshError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def __init__(self, polygon, world_matrix, triangle_obj, mesh_type, mesh):
        super(HgeTriangle, self).__init__()
        self.vertices = []
        if len(polygon.vertices) > 3:
            raise self.UntriangulatedMeshError("Your mesh must be triangulated before exporting.")
        for vertex_index, loop_index in zip(polygon.vertices, polygon.loop_indices):
            vertex = HgeVertex(vertex_index, loop_index, triangle_obj, world_matrix, mesh_type, mesh)
            self.vertices.append(vertex)
        # mid_normal = self.vertices[0].normal + self.vertices[1].normal + self.vertices[2].normal
        # v1 = self.vertices[1].position - self.vertices[0].position
        # v2 = self.vertices[2].position - self.vertices[0].position
        # cross_v1_v2 = v1.cross(v2)
        # cull = cross_v1_v2.dot(mid_normal)
        # if cull > 0:
        v = self.vertices[2]
        self.vertices[2] = self.vertices[1]
        self.vertices[1] = v

    def __str__(self):
        s = ''
        for v in self.vertices:
            s += str(v)
            s += '\n'
        return s


class HgeMesh:
    MESH_TYPE_STATIC = 'static'
    MESH_TYPE_OCCLUSION = 'occlusion'
    MESH_TYPE_SKIN = 'skin'

    def __init__(self, mesh_obj, mesh_type=MESH_TYPE_STATIC):
        self.max_number_of_affecting_bone_on_a_vertex = 0
        triangles = []
        world_matrix = mesh_obj.matrix_world
        for polygon in mesh_obj.data.polygons:
            triangle = HgeTriangle(polygon, world_matrix, mesh_obj, mesh_type, self)
            triangles.append(triangle)
        vert_ind = dict()
        vertices_count = 0
        for triangle in triangles:
            for vertex in triangle.vertices:
                if mesh_type == self.MESH_TYPE_SKIN:
                    vertex.create_data()
                key = vertex.data
                if key in vert_ind:
                    vert_ind[key].append(vertices_count)
                else:
                    vert_ind[key] = [vertices_count]
                vertices_count += 1
        self.ibo = vertices_count * [0]
        self.vbo = []
        vertices_count = 0
        for vertex, indices in vert_ind.items():
            for v in vertex:
                self.vbo.append(v)
            for i in indices:
                self.ibo[i] = vertices_count
            vertices_count += 1
        if mesh_type == self.MESH_TYPE_SKIN:
            print("Maximum number of affecting bone an a vertex is: ", self.max_number_of_affecting_bone_on_a_vertex)

    def save(self, save_file):
        save_file.write(TYPE_VERTEX_ELEMENT_COUNT(len(self.vbo)))
        for f in self.vbo:
            save_file.write(TYPE_VERTEX_ELEMENT(f))
        save_file.write(TYPE_INDICES_COUNT(len(self.ibo)))
        for i in self.ibo:
            save_file.write(TYPE_INDEX_ELEMENT(i))


class HgeBone:
    BONE_TYPE_FLOAT = ctypes.c_float
    BONE_TYPE_BONE_INDEX = ctypes.c_uint16
    BONE_TYPE_CHILDREN_COUNT = ctypes.c_uint8

    class OutOfRangeChildrenNumberError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def __init__(self, bone):
        self.name = bone.name
        if len(bone.children) > 255:
            raise self.OutOfRangeChildrenNumberError("Your bone structure has out of range children at bone[",
                                                     self.name, "]")
        self.children = [HgeBone(child) for child in bone.children]
        self.head = bone.head
        self.tail = bone.tail
        self.index = None

    def indexify(self, vertex_groups):
        self.index = vertex_groups[self.name]
        for c in self.children:
            c.indexify(vertex_groups)

    def save(self, save_file):
        save_string(save_file, self.name)
        for i in range(3):
            save_file.write(self.BONE_TYPE_FLOAT(self.head[i]))
        for i in range(3):
            save_file.write(self.BONE_TYPE_FLOAT(self.tail[i]))
        save_file.write(self.BONE_TYPE_BONE_INDEX(self.index))
        print(len(self.children))
        save_file.write(self.BONE_TYPE_CHILDREN_COUNT(len(self.children)))
        for c in self.children:
            c.save(save_file)


class HgeChannelKeyFrame:
    CHANNEL_KEYFRAME_TYPE_ELEMENT = ctypes.c_float

    def __init__(self, keyframe):
        if keyframe.interpolation != 'BEZIER':
            print("Error: Only bezier interpolation is supported.")
            exit(1)
        self.position_t = keyframe.co[0]
        self.position_v = keyframe.co[1]
        self.left_handle_t = keyframe.handle_left[0]
        self.left_handle_v = keyframe.handle_left[1]
        self.right_handle_t = keyframe.handle_right[0]
        self.right_handle_v = keyframe.handle_right[1]

    def save(self, save_file):
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.position_t))
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.position_v))
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.left_handle_t))
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.left_handle_v))
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.right_handle_t))
        save_file.write(self.CHANNEL_KEYFRAME_TYPE_ELEMENT(self.right_handle_v))


class HgeAnimationChannel:
    X_LOCATION = ctypes.c_uint8(1)
    Y_LOCATION = ctypes.c_uint8(2)
    Z_LOCATION = ctypes.c_uint8(3)
    W_QUATERNION_ROTATION = ctypes.c_uint8(4)
    X_QUATERNION_ROTATION = ctypes.c_uint8(5)
    Y_QUATERNION_ROTATION = ctypes.c_uint8(6)
    Z_QUATERNION_ROTATION = ctypes.c_uint8(7)
    X_SCALE = ctypes.c_uint8(8)
    Y_SCALE = ctypes.c_uint8(9)
    Z_SCALE = ctypes.c_uint8(10)

    CHANNEL_TYPE_KEYFRAME_COUNT = ctypes.c_uint16

    def __init__(self, channel):
        self.bone_index = None
        self.keyframes = []
        data_path = channel.data_path
        array_index = channel.array_index
        if postfix_check(data_path, 'location'):
            self.bone = data_path[len('pose.bones[\"'):len(data_path)-len('\"].location')]
            if array_index == 0:
                self.channel_type = self.X_LOCATION
            elif array_index == 1:
                self.channel_type = self.Y_LOCATION
            elif array_index == 2:
                self.channel_type = self.Z_LOCATION
            else:
                print("Error: Unknown location channel.")
                exit(1)
        elif postfix_check(data_path, 'rotation_quaternion'):
            self.bone = data_path[len('pose.bones[\"'):len(data_path)-len('\"].rotation_quaternion')]
            if array_index == 0:
                self.channel_type = self.W_QUATERNION_ROTATION
            elif array_index == 1:
                self.channel_type = self.X_QUATERNION_ROTATION
            elif array_index == 2:
                self.channel_type = self.Y_QUATERNION_ROTATION
            elif array_index == 3:
                self.channel_type = self.Z_QUATERNION_ROTATION
            else:
                print("Error: Unknown rotation quaternion channel.")
                exit(1)
        elif postfix_check(data_path, 'scale'):
            self.bone = data_path[len('pose.bones[\"'):len(data_path)-len('\"].scale')]
            if array_index == 0:
                self.channel_type = self.X_SCALE
            elif array_index == 1:
                self.channel_type = self.Y_SCALE
            elif array_index == 2:
                self.channel_type = self.Z_SCALE
            else:
                print("Error: Unknown scale channel.")
                exit(1)
        else:
            print("Error: Unknown channel.")
            exit(1)
        for keyframe in channel.keyframe_points:
            self.keyframes.append(HgeChannelKeyFrame(keyframe))

    def indexify(self, vertex_groups):
        self.bone_index = vertex_groups[self.bone]

    def save(self, save_file):
        save_file.write(self.channel_type)
        save_file.write(HgeBone.BONE_TYPE_BONE_INDEX(self.bone_index))
        save_string(save_file, self.bone)
        save_file.write(self.CHANNEL_TYPE_KEYFRAME_COUNT(len(self.keyframes)))
        for k in self.keyframes:
            k.save(save_file)


class HgeAction:
    ACTION_TYPE_FRAME_RANGE = ctypes.c_float
    ACTION_TYPE_CHANNEL_COUNT = ctypes.c_int16

    def __init__(self, arm_obj):
        action = arm_obj.animation_data.action
        self.key_frames_range = action.frame_range
        self.channels = []
        for fcurve in action.fcurves:
            self.channels.append(HgeAnimationChannel(fcurve))

    def indexify_channels_bones(self, vertex_groups):
        for c in self.channels:
            c.indexify(vertex_groups)

    def save(self, save_file):
        save_file.write(self.ACTION_TYPE_FRAME_RANGE(self.key_frames_range[0]))
        save_file.write(self.ACTION_TYPE_FRAME_RANGE(self.key_frames_range[1]))
        save_file.write(self.ACTION_TYPE_CHANNEL_COUNT(len(self.channels)))
        for c in self.channels:
            c.save(save_file)


class HgeAnimation:

    def __init__(self, arm_obj):
        self.action = HgeAction(arm_obj)

    def save(self, save_file):
        self.action.save(save_file)

    def indexify_channels_bones(self, vertex_groups):
        self.action.indexify_channels_bones(vertex_groups)


class HgeArmature:
    ARMATURE_TYPE_BONE_COUNT = ctypes.c_uint16
    ARMATURE_TYPE_MAX_NUMBER_OF_AFFECTING_BONE_ON_A_VERTEX_TYPE = ctypes.c_int8

    def __init__(self, arm_obj):
        self.name = arm_obj.name
        self.bones = []
        for bone in arm_obj.pose.bones:
            if bone.parent is None:
                self.bones.append(HgeBone(bone))
        if len(self.bones) > 1:
            print("Warning: Number of root bone in ", self.name, " is ", len(self.bones))
        self.animation_data = HgeAnimation(arm_obj)
        self.skin = HgeMesh(arm_obj.children[0], HgeMesh.MESH_TYPE_SKIN)
        vertex_groups = arm_obj.children[0].vertex_groups
        vertex_groups = {g.name: i for i, g in enumerate(vertex_groups)}
        self.animation_data.indexify_channels_bones(vertex_groups)
        for b in self.bones:
            b.indexify(vertex_groups)

    def save(self, save_file):
        save_file.write(OBJECT_TYPE_ID_ARMATURE)
        save_string(save_file, self.name)
        save_file.write(self.ARMATURE_TYPE_BONE_COUNT(len(self.bones)))
        for b in self.bones:
            b.save(save_file)
        self.animation_data.save(save_file)
        save_file.write(self.ARMATURE_TYPE_MAX_NUMBER_OF_AFFECTING_BONE_ON_A_VERTEX_TYPE(
            self.skin.max_number_of_affecting_bone_on_a_vertex))
        self.skin.save(save_file)


class HgeGeometry():

    def __init__(self, geo_obj):
        self.name = geo_obj.name
        self.mesh = HgeMesh(geo_obj)
        self.occ_mesh = None
        occ_mesh_name = PREFIX_OCCLUSION_TEST + self.name
        for occ_obj in bpy.data.objects:
            if occ_obj.type == OBJECT_TYPE_STRING_MESH and occ_obj.name == occ_mesh_name:
                self.occ_mesh = HgeMesh(occ_obj, HgeMesh.MESH_TYPE_OCCLUSION)
                break

    def save(self, save_file):
        save_file.write(OBJECT_TYPE_ID_GEOMETRY)
        save_string(save_file, self.name)
        self.mesh.save(save_file)
        if self.occ_mesh is None:
            save_file.write(BOOLEAN_FALSE)
        else:
            save_file.write(BOOLEAN_TRUE)
            self.occ_mesh.save(save_file)


class HgeScene():

    def __init__(self):
        super(HgeScene, self).__init__()
        self.objects = []

    def add_object(self, o):
        self.objects.append(o)

    def save(self, save_file):
        for o in self.objects:
            o.save(save_file)


file = open("/home/thany/QtCreator/build-HGE-Desktop-Debug/hge-sample.hge", "wb")
scene = HgeScene()
for obj in bpy.data.objects:
    if obj.type == OBJECT_TYPE_STRING_MESH:
        if prefix_check(obj.name, PREFIX_OCCLUSION_TEST):
            continue
        elif prefix_check(obj.name, PREFIX_SKIN):
            continue
        else:
            if obj.parent is not None:
                print("Error: Your static mesh must not have parent.")
                exit(0)
            geo = HgeGeometry(obj)
            scene.add_object(geo)
    elif obj.type == OBJECT_TYPE_STRING_ARMATURE:
        print("clvmdfkjkfjkfjdkhvifjdkvhkj")
        if prefix_check(obj.name, PREFIX_SKELETON):
            print("Skeleton Armature is not supported yet")
            exit(1)
        else:
            scene.add_object(HgeArmature(obj))
# Endian
if sys.byteorder == 'little':
    file.write(ctypes.c_char(1))
else:
    file.write(ctypes.c_char(0))
scene.save(file)
file.close()
scene = None
