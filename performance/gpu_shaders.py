"""
performance/gpu_shaders.py
GLSL 1.30 shader sources for GPU Pulse.

#version 130 is chosen deliberately:
  - OpenGL 3.0 (2008) — supported on every GPU since ~2010
  - Allows `break` inside `for` (1.20 forbids it in strict mode)
  - Allows `in`/`out` (1.20 needs attribute/varying)
  - No core-profile VAO requirement (works on compat profiles)
"""

FILL_VERTEX_SRC = """
#version 130
in vec2 a_pos;
out vec2 uv;
void main() {
    uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

FILL_FRAGMENT_SRC = """
#version 130
in vec2 uv;
out vec4 frag;
uniform float u_time;
void main() {
    float r = 0.5 + 0.5 * sin(u_time * 0.5 + uv.x * 3.0);
    float g = 0.5 + 0.5 * sin(u_time * 0.7 + uv.y * 3.0);
    float b = 0.5 + 0.5 * sin(u_time * 0.9 + uv.x * uv.y * 3.0);
    frag = vec4(r, g, b, 1.0);
}
"""

ALU_VERTEX_SRC = FILL_VERTEX_SRC

ALU_FRAGMENT_SRC = """
#version 130
in vec2 uv;
out vec4 frag;
uniform float u_time;
uniform int   u_max_iter;
void main() {
    float angle = u_time * 0.05;
    mat2 R = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
    vec2 p = R * ((uv - 0.5) * 3.5);
    vec2 z = vec2(0.0);
    int iter = 0;
    for (int i = 0; i < 128; i++) {
        z = vec2(z.x*z.x - z.y*z.y + p.x,
                 2.0*z.x*z.y         + p.y);
        if (dot(z, z) > 4.0) break;
        iter = i;
    }
    float t = float(iter) / float(u_max_iter);
    frag = vec4(
        0.5 + 0.5 * cos(6.28 * (t + 0.0)),
        0.5 + 0.5 * cos(6.28 * (t + 0.33)),
        0.5 + 0.5 * cos(6.28 * (t + 0.66)),
        1.0
    );
}
"""