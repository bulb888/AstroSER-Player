"""OpenGL-accelerated image viewer with GPU-based adjustments."""

import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QPainter, QFont, QColor, QSurfaceFormat, QPen, QBrush
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import (
    QOpenGLShaderProgram, QOpenGLShader, QOpenGLTexture, QOpenGLBuffer,
    QOpenGLVertexArrayObject,
)
from OpenGL import GL

from .i18n import tr, I18n

# Vertex shader: fullscreen quad with zoom/pan
VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

uniform vec2 u_offset;
uniform float u_zoom;
uniform vec2 u_viewport;
uniform vec2 u_imageSize;

out vec2 vTexCoord;

void main() {
    // Compute aspect-correct quad
    vec2 imgAspect = u_imageSize / max(u_imageSize.x, u_imageSize.y);
    vec2 vpAspect = u_viewport / max(u_viewport.x, u_viewport.y);

    vec2 scale = imgAspect / vpAspect;
    vec2 pos = aPos * scale * u_zoom + u_offset;

    gl_Position = vec4(pos, 0.0, 1.0);
    vTexCoord = aTexCoord;
}
"""

# Fragment shader: applies debayer + all adjustments on GPU
FRAGMENT_SHADER = """
#version 330 core
in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D u_texture;
uniform sampler1D u_solarLut;

uniform float u_brightness;
uniform float u_contrast;
uniform float u_gamma;
uniform float u_autoLo;
uniform float u_autoHi;
uniform bool u_autoStretch;
uniform bool u_solarColorize;
uniform bool u_isMono;
uniform float u_maxVal;

// Bayer demosaic uniforms
uniform bool u_isBayer;
uniform vec2 u_bayerRedOffset;   // (col, row) of red pixel in 2x2 block
uniform vec2 u_bayerBlueOffset;  // (col, row) of blue pixel in 2x2 block

float fetchBayer(ivec2 p, ivec2 sz) {
    p = clamp(p, ivec2(0), sz - 1);
    return texelFetch(u_texture, p, 0).r;
}

vec3 debayer_bilinear(vec2 texCoord) {
    ivec2 sz = textureSize(u_texture, 0);
    ivec2 pix = ivec2(texCoord * vec2(sz));
    pix = clamp(pix, ivec2(0), sz - 1);

    // Integer Bayer block position — no float precision issues
    ivec2 blockPos = pix % 2;
    ivec2 rOff = ivec2(u_bayerRedOffset + 0.5);
    ivec2 bOff = ivec2(u_bayerBlueOffset + 0.5);

    float c  = fetchBayer(pix, sz);
    float t  = fetchBayer(pix + ivec2( 0, -1), sz);
    float b  = fetchBayer(pix + ivec2( 0,  1), sz);
    float l  = fetchBayer(pix + ivec2(-1,  0), sz);
    float r  = fetchBayer(pix + ivec2( 1,  0), sz);
    float tl = fetchBayer(pix + ivec2(-1, -1), sz);
    float tr = fetchBayer(pix + ivec2( 1, -1), sz);
    float bl = fetchBayer(pix + ivec2(-1,  1), sz);
    float br = fetchBayer(pix + ivec2( 1,  1), sz);

    float red, green, blue;

    if (blockPos == rOff) {
        // Red pixel
        red = c;
        green = (t + b + l + r) * 0.25;
        blue = (tl + tr + bl + br) * 0.25;
    } else if (blockPos == bOff) {
        // Blue pixel
        blue = c;
        green = (t + b + l + r) * 0.25;
        red = (tl + tr + bl + br) * 0.25;
    } else if (blockPos.y == rOff.y) {
        // Green pixel on red row
        red = (l + r) * 0.5;
        green = c;
        blue = (t + b) * 0.5;
    } else {
        // Green pixel on blue row
        blue = (l + r) * 0.5;
        green = c;
        red = (t + b) * 0.5;
    }

    return vec3(red, green, blue);
}

void main() {
    vec3 color;

    if (u_isBayer) {
        color = debayer_bilinear(vTexCoord);
        color *= u_maxVal;
    } else {
        vec4 texel = texture(u_texture, vTexCoord);
        if (u_isMono) {
            float v = texel.r;
            color = vec3(v, v, v);
        } else {
            color = texel.rgb;
        }
        // GL auto-normalizes integer textures to [0,1] based on type max (255 or 65535).
        // u_maxVal is the rescale factor: typeMax / pixelMax (e.g. 65535/4095 for 12-bit).
        color *= u_maxVal;
    }

    // Auto stretch
    if (u_autoStretch && u_autoHi > u_autoLo) {
        color = (color - u_autoLo) / (u_autoHi - u_autoLo);
    }

    // Contrast and brightness
    color = color * u_contrast + u_brightness;

    // Gamma
    color = clamp(color, 0.0, 1.0);
    if (u_gamma != 1.0) {
        color = pow(color, vec3(1.0 / u_gamma));
    }

    color = clamp(color, 0.0, 1.0);

    // Solar false color
    if (u_solarColorize) {
        float gray = dot(color, vec3(0.299, 0.587, 0.114));
        color = texture(u_solarLut, gray).rgb;
    }

    FragColor = vec4(color, 1.0);
}
"""


class GLImageViewer(QOpenGLWidget):
    """OpenGL-based image viewer with GPU adjustments, zoom and pan."""

    zoom_changed = Signal(float)
    roi_changed = Signal(tuple)

    def __init__(self, parent=None):
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__(parent)
        self.setFormat(fmt)

        self._zoom = 1.0
        self._min_zoom = 0.05
        self._max_zoom = 20.0
        self._offset = QPointF(0.0, 0.0)
        self._has_image = False
        self._img_width = 0
        self._img_height = 0

        # Adjustment uniforms
        self.brightness = 0.0
        self.contrast = 1.0
        self.gamma = 1.0
        self.auto_stretch = False
        self.auto_lo = 0.0
        self.auto_hi = 1.0
        self.solar_colorize = False
        self.is_mono = True
        self.is_bayer = False
        self.bayer_red_offset = (0.0, 0.0)
        self.bayer_blue_offset = (1.0, 1.0)
        self.max_val = 1.0

        # Mouse pan state
        self._panning = False
        self._last_mouse = QPointF()

        # ROI state (in image pixel coordinates)
        self._roi_rect: list[int] | None = None  # [x, y, w, h]
        self._roi_dragging = False
        self._roi_drag_start = QPointF()
        self._roi_start_rect: list[int] | None = None

        # GL objects (initialized in initializeGL)
        self._program = None
        self._vao = None
        self._vbo = None
        self._texture = None
        self._solar_lut_tex = None
        self._gl_initialized = False

        # Pending frame data to upload
        self._pending_frame = None

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        I18n.instance().language_changed.connect(lambda _: self.update())

    def initializeGL(self):
        GL.glClearColor(0.117, 0.117, 0.117, 1.0)  # rgb(30,30,30)

        # Shader program
        self._program = QOpenGLShaderProgram(self)
        self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER)
        self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT_SHADER)
        self._program.link()

        # Cache uniform locations
        pid = self._program.programId()
        self._u_zoom = GL.glGetUniformLocation(pid, "u_zoom")
        self._u_offset = GL.glGetUniformLocation(pid, "u_offset")
        self._u_viewport = GL.glGetUniformLocation(pid, "u_viewport")
        self._u_imageSize = GL.glGetUniformLocation(pid, "u_imageSize")
        self._u_brightness = GL.glGetUniformLocation(pid, "u_brightness")
        self._u_contrast = GL.glGetUniformLocation(pid, "u_contrast")
        self._u_gamma = GL.glGetUniformLocation(pid, "u_gamma")
        self._u_autoLo = GL.glGetUniformLocation(pid, "u_autoLo")
        self._u_autoHi = GL.glGetUniformLocation(pid, "u_autoHi")
        self._u_autoStretch = GL.glGetUniformLocation(pid, "u_autoStretch")
        self._u_solarColorize = GL.glGetUniformLocation(pid, "u_solarColorize")
        self._u_isMono = GL.glGetUniformLocation(pid, "u_isMono")
        self._u_maxVal = GL.glGetUniformLocation(pid, "u_maxVal")
        self._u_isBayer = GL.glGetUniformLocation(pid, "u_isBayer")
        self._u_bayerRedOffset = GL.glGetUniformLocation(pid, "u_bayerRedOffset")
        self._u_bayerBlueOffset = GL.glGetUniformLocation(pid, "u_bayerBlueOffset")
        self._u_texture = GL.glGetUniformLocation(pid, "u_texture")
        self._u_solarLut = GL.glGetUniformLocation(pid, "u_solarLut")

        # Fullscreen quad: positions + texcoords
        vertices = np.array([
            # pos        texcoord
            -1.0, -1.0,  0.0, 1.0,
             1.0, -1.0,  1.0, 1.0,
            -1.0,  1.0,  0.0, 0.0,
             1.0,  1.0,  1.0, 0.0,
        ], dtype=np.float32)

        self._vao = QOpenGLVertexArrayObject(self)
        self._vao.create()
        self._vao.bind()

        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._vbo.create()
        self._vbo.bind()
        self._vbo.allocate(vertices.tobytes(), vertices.nbytes)

        self._program.bind()
        self._program.enableAttributeArray(0)
        self._program.setAttributeBuffer(0, GL.GL_FLOAT, 0, 2, 16)
        self._program.enableAttributeArray(1)
        self._program.setAttributeBuffer(1, GL.GL_FLOAT, 8, 2, 16)
        self._program.release()

        self._vbo.release()
        self._vao.release()

        # Build solar LUT texture
        self._build_solar_lut_texture()

        self._gl_initialized = True

        # Upload pending frame if any
        if self._pending_frame is not None:
            self._upload_texture(self._pending_frame)
            self._pending_frame = None

    def _build_solar_lut_texture(self):
        """Create 1D texture for solar false color."""
        x = np.linspace(0, 1, 256)
        lut = np.zeros((256, 3), dtype=np.uint8)
        lut[:, 0] = (np.clip(x * 1.8, 0, 1) * 255).astype(np.uint8)
        lut[:, 1] = (np.clip((x - 0.15) * 1.2, 0, 1) ** 0.9 * 255).astype(np.uint8)
        lut[:, 2] = (np.clip((x - 0.5) * 1.5, 0, 1) ** 1.2 * 200).astype(np.uint8)

        GL.glActiveTexture(GL.GL_TEXTURE1)
        self._solar_lut_tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self._solar_lut_tex)
        GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_RGB8, 256, 0,
                        GL.GL_RGB, GL.GL_UNSIGNED_BYTE, lut.tobytes())
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glActiveTexture(GL.GL_TEXTURE0)

    def set_frame(self, frame: np.ndarray, is_mono: bool, max_val: float,
                  auto_lo: float = 0.0, auto_hi: float = 1.0):
        """Upload a frame to GPU texture. Frame should be debayered already."""
        self._img_width = frame.shape[1]
        self._img_height = frame.shape[0]
        self.is_mono = is_mono
        self.max_val = max_val
        self.auto_lo = auto_lo
        self.auto_hi = auto_hi

        if not self._gl_initialized:
            self._pending_frame = frame
            self._has_image = True
            return

        self._upload_texture(frame)
        self._has_image = True
        self.update()

    def _upload_texture(self, frame: np.ndarray):
        """Upload numpy array as OpenGL texture."""
        self.makeCurrent()

        h, w = frame.shape[0], frame.shape[1]
        is_16bit = frame.dtype == np.uint16

        if self._texture is not None:
            GL.glDeleteTextures([self._texture])

        self._texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)

        # Set alignment for tightly packed data
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)

        frame_c = np.ascontiguousarray(frame)

        if frame.ndim == 2:
            # Mono
            if is_16bit:
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R16, w, h, 0,
                                GL.GL_RED, GL.GL_UNSIGNED_SHORT, frame_c.tobytes())
            else:
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R8, w, h, 0,
                                GL.GL_RED, GL.GL_UNSIGNED_BYTE, frame_c.tobytes())
        else:
            # RGB
            if is_16bit:
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGB16, w, h, 0,
                                GL.GL_RGB, GL.GL_UNSIGNED_SHORT, frame_c.tobytes())
            else:
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGB8, w, h, 0,
                                GL.GL_RGB, GL.GL_UNSIGNED_BYTE, frame_c.tobytes())

        # Bayer textures need NEAREST to preserve exact pixel values for demosaic
        filt = GL.GL_NEAREST if self.is_bayer else GL.GL_LINEAR
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, filt)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)

        self.doneCurrent()

    def paintGL(self):
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        if not self._has_image or self._texture is None:
            return

        self._program.bind()

        # Set uniforms using cached locations
        GL.glUniform1f(self._u_zoom, self._zoom)
        GL.glUniform2f(self._u_offset, self._offset.x(), self._offset.y())
        GL.glUniform2f(self._u_viewport, float(self.width()), float(self.height()))
        GL.glUniform2f(self._u_imageSize, float(self._img_width), float(self._img_height))

        GL.glUniform1f(self._u_brightness, self.brightness)
        GL.glUniform1f(self._u_contrast, self.contrast)
        GL.glUniform1f(self._u_gamma, self.gamma)
        GL.glUniform1f(self._u_autoLo, self.auto_lo)
        GL.glUniform1f(self._u_autoHi, self.auto_hi)
        GL.glUniform1i(self._u_autoStretch, int(self.auto_stretch))
        GL.glUniform1i(self._u_solarColorize, int(self.solar_colorize))
        GL.glUniform1i(self._u_isMono, int(self.is_mono))
        GL.glUniform1f(self._u_maxVal, self.max_val)
        GL.glUniform1i(self._u_isBayer, int(self.is_bayer))
        GL.glUniform2f(self._u_bayerRedOffset, *self.bayer_red_offset)
        GL.glUniform2f(self._u_bayerBlueOffset, *self.bayer_blue_offset)

        # Bind textures
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)
        GL.glUniform1i(self._u_texture, 0)

        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self._solar_lut_tex)
        GL.glUniform1i(self._u_solarLut, 1)

        # Draw image
        self._vao.bind()
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        self._vao.release()
        self._program.release()

        # Draw ROI overlay using QPainter (must be after GL drawing)
        if self._roi_rect is not None:
            self._draw_roi_overlay()

    def _draw_roi_overlay(self) -> None:
        """Draw ROI rectangle using QPainter on top of GL content."""
        rx, ry, rw, rh = self._roi_rect
        p1 = self._image_to_widget(rx, ry)
        p2 = self._image_to_widget(rx + rw, ry + rh)

        painter = QPainter(self)
        painter.beginNativePainting()
        painter.endNativePainting()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(0, 255, 0, 200))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(p1, p2))
        painter.end()

    def paintEvent(self, event):
        """Override to draw welcome hint when no image."""
        super().paintEvent(event)
        if not self._has_image:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("welcome_hint"))
            painter.end()

    # --- Zoom / Pan ---

    def fit_in_view(self):
        if not self._has_image:
            return
        vw, vh = self.width(), self.height()
        iw, ih = self._img_width, self._img_height
        scale_x = vw / iw
        scale_y = vh / ih
        self._zoom = min(scale_x, scale_y)
        self._offset = QPointF(0.0, 0.0)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_zoom(self, factor: float):
        if not self._has_image:
            return
        self._zoom = max(self._min_zoom, min(self._max_zoom, factor))
        self.zoom_changed.emit(self._zoom)
        self.update()

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            scale = 1.15
        elif delta < 0:
            scale = 1.0 / 1.15
        else:
            return

        new_zoom = self._zoom * scale
        if self._min_zoom <= new_zoom <= self._max_zoom:
            # Zoom toward mouse position
            mouse_ndc_x = (event.position().x() / self.width()) * 2.0 - 1.0
            mouse_ndc_y = -((event.position().y() / self.height()) * 2.0 - 1.0)

            # Adjust offset so the point under mouse stays fixed
            self._offset = QPointF(
                mouse_ndc_x - scale * (mouse_ndc_x - self._offset.x()),
                mouse_ndc_y - scale * (mouse_ndc_y - self._offset.y()),
            )
            self._zoom = new_zoom
            self.zoom_changed.emit(self._zoom)
            self.update()

    def _is_inside_roi(self, pos: QPointF) -> bool:
        """Check if a widget position is inside the ROI rectangle."""
        if self._roi_rect is None or not self._has_image:
            return False
        rx, ry, rw, rh = self._roi_rect
        p1 = self._image_to_widget(rx, ry)
        p2 = self._image_to_widget(rx + rw, ry + rh)
        roi_screen = QRectF(p1, p2).normalized()
        return roi_screen.contains(pos)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_inside_roi(event.position()):
                self._roi_dragging = True
                self._roi_drag_start = event.position()
                self._roi_start_rect = list(self._roi_rect)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self._panning = True
                self._last_mouse = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._roi_dragging and self._roi_start_rect is not None:
            # Convert drag delta to image coordinates
            start_img = self._widget_to_image(
                self._roi_drag_start.x(), self._roi_drag_start.y())
            cur_img = self._widget_to_image(
                event.position().x(), event.position().y())
            dx = int(cur_img.x() - start_img.x())
            dy = int(cur_img.y() - start_img.y())
            new_x = max(0, min(self._img_width - self._roi_start_rect[2],
                               self._roi_start_rect[0] + dx))
            new_y = max(0, min(self._img_height - self._roi_start_rect[3],
                               self._roi_start_rect[1] + dy))
            self._roi_rect[0] = new_x
            self._roi_rect[1] = new_y
            self.update()
            self.roi_changed.emit(tuple(self._roi_rect))
        elif self._panning:
            delta = event.position() - self._last_mouse
            self._offset = QPointF(
                self._offset.x() + delta.x() / self.width() * 2.0,
                self._offset.y() - delta.y() / self.height() * 2.0,
            )
            self._last_mouse = event.position()
            self.update()
        else:
            # Update cursor when hovering over ROI
            if self._is_inside_roi(event.position()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._roi_dragging:
                self._roi_dragging = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif self._panning:
                self._panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.fit_in_view()

    def reset_view(self):
        self._has_image = False
        self._offset = QPointF(0.0, 0.0)
        self._zoom = 1.0

    # --- Drag and Drop ---

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.ser'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.ser'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.ser'):
                event.acceptProposedAction()
                window = self.window()
                if hasattr(window, 'open_file'):
                    window.open_file(filepath)
                return

    # --- ROI ---

    def set_roi(self, x: int, y: int, w: int, h: int) -> None:
        """Set ROI rectangle in image pixel coordinates."""
        self._roi_rect = [x, y, w, h]
        self.update()

    def clear_roi(self) -> None:
        self._roi_rect = None
        self._roi_dragging = False
        self.update()

    def get_roi(self) -> tuple[int, int, int, int] | None:
        if self._roi_rect is None:
            return None
        return tuple(self._roi_rect)

    def _image_to_widget(self, ix: float, iy: float) -> QPointF:
        """Convert image pixel coords to widget coords."""
        vw, vh = float(self.width()), float(self.height())
        iw, ih = float(self._img_width), float(self._img_height)

        img_aspect = [iw / max(iw, ih), ih / max(iw, ih)]
        vp_aspect = [vw / max(vw, vh), vh / max(vw, vh)]
        sx = img_aspect[0] / vp_aspect[0]
        sy = img_aspect[1] / vp_aspect[1]

        # image (ix, iy) -> texcoord -> aPos
        apos_x = (ix / iw) * 2.0 - 1.0
        apos_y = 1.0 - (iy / ih) * 2.0

        ndc_x = apos_x * sx * self._zoom + self._offset.x()
        ndc_y = apos_y * sy * self._zoom + self._offset.y()

        wx = (ndc_x + 1.0) / 2.0 * vw
        wy = (1.0 - ndc_y) / 2.0 * vh
        return QPointF(wx, wy)

    def _widget_to_image(self, wx: float, wy: float) -> QPointF:
        """Convert widget coords to image pixel coords."""
        vw, vh = float(self.width()), float(self.height())
        iw, ih = float(self._img_width), float(self._img_height)

        img_aspect = [iw / max(iw, ih), ih / max(iw, ih)]
        vp_aspect = [vw / max(vw, vh), vh / max(vw, vh)]
        sx = img_aspect[0] / vp_aspect[0]
        sy = img_aspect[1] / vp_aspect[1]

        ndc_x = wx / vw * 2.0 - 1.0
        ndc_y = 1.0 - wy / vh * 2.0

        apos_x = (ndc_x - self._offset.x()) / (sx * self._zoom)
        apos_y = (ndc_y - self._offset.y()) / (sy * self._zoom)

        ix = (apos_x + 1.0) / 2.0 * iw
        iy = (1.0 - apos_y) / 2.0 * ih
        return QPointF(ix, iy)

    @property
    def zoom_factor(self) -> float:
        return self._zoom
