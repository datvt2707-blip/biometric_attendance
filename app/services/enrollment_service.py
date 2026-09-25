"""Transactional employee/student profile and four-sample face enrollment."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import uuid

import cv2
import numpy as np

from app.database.database import DEFAULT_DATABASE_PATH, PROJECT_ROOT, connect, initialize_database, transaction
from app.database.models.class_model import Enrollment
from app.database.models.face import FaceEmbedding, FaceImage
from app.database.models.user import Employee, Person, Student
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.face_repository import FaceRepository
from app.database.repositories.user_repository import UserRepository
from app.biometric.preprocessing.image_preprocessing import crop_face


SAMPLE_LABELS = ("front", "left", "right", "up")


class EnrollmentValidationError(ValueError):
    """Enrollment sample or form data failed validation."""


class EnrollmentConflictError(RuntimeError):
    """A code or related record conflicts with existing database data."""


@dataclass(frozen=True)
class EnrollmentSample:
    frame: np.ndarray
    bbox: tuple[float, float, float, float]
    embedding: np.ndarray
    status: str = "face_selected"
    face_count: int = 1
    model_name: str = "buffalo_l"
    model_version: str = "w600k_r50.onnx"


def validate_samples(samples):
    """Validate four distinct accepted captures and return normalized vectors/crops."""
    if len(samples) != 4:
        raise EnrollmentValidationError("Cần đúng bốn mẫu khuôn mặt.")
    validated, seen_frames, seen_vectors = [], set(), set()
    dimension = None
    model_identity = None
    for index, sample in enumerate(samples):
        status = getattr(sample, "status", None)
        face_count = getattr(sample, "face_count", None)
        frame = getattr(sample, "frame", None)
        bbox = getattr(sample, "bbox", None)
        vector = getattr(sample, "embedding", None)
        if status != "face_selected" or face_count != 1 or bbox is None:
            raise EnrollmentValidationError(f"Mẫu {index + 1} không có duy nhất một khuôn mặt được chọn an toàn.")
        if not isinstance(frame, np.ndarray) or frame.size == 0 or frame.ndim not in (2, 3):
            raise EnrollmentValidationError(f"Ảnh của mẫu {index + 1} không hợp lệ.")
        crop = crop_face(frame, bbox)
        frame_hash = hashlib.sha256(crop.tobytes() + repr(crop.shape).encode("ascii")).digest()
        if frame_hash in seen_frames:
            raise EnrollmentValidationError("Không thể dùng lại cùng một ảnh cho nhiều mẫu.")
        seen_frames.add(frame_hash)

        values = np.asarray(vector, dtype=np.float32)
        if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
            raise EnrollmentValidationError(f"Embedding mẫu {index + 1} sai định dạng hoặc chứa giá trị không hữu hạn.")
        if dimension is None:
            dimension = int(values.size)
        elif values.size != dimension:
            raise EnrollmentValidationError("Kích thước embedding giữa các mẫu không đồng nhất.")
        norm = float(np.linalg.norm(values))
        if not np.isfinite(norm) or norm <= 0:
            raise EnrollmentValidationError(f"Embedding mẫu {index + 1} có chuẩn không hợp lệ.")
        identity = (getattr(sample, "model_name", ""), getattr(sample, "model_version", ""))
        if not all(identity):
            raise EnrollmentValidationError(f"Thiếu định danh model thật ở mẫu {index + 1}.")
        if model_identity is None:
            model_identity = identity
        elif identity != model_identity:
            raise EnrollmentValidationError("Các mẫu được tạo từ model khác nhau.")
        values = np.ascontiguousarray(values / norm, dtype="<f4")
        vector_hash = hashlib.sha256(values.tobytes()).digest()
        if vector_hash in seen_vectors:
            raise EnrollmentValidationError("Không thể dùng lại cùng một embedding cho nhiều mẫu.")
        seen_vectors.add(vector_hash)
        validated.append((crop, values, *identity))
    return tuple(validated)


class EnrollmentCaptureSession:
    """Stateful four-step capture gate used by the enrollment dialog and tests."""

    def __init__(self):
        self.samples = []
        self._frame_hashes = set()
        self._embedding_hashes = set()

    def accept(self, frame, result):
        if len(self.samples) >= 4:
            raise EnrollmentValidationError("Đã thu đủ bốn mẫu.")
        if (getattr(result, "status", None) != "face_selected"
                or getattr(result, "face_count", None) != 1
                or getattr(result, "selected", None) is None
                or getattr(result, "embedding", None) is None):
            raise EnrollmentValidationError("Cần đúng một khuôn mặt được chọn an toàn.")
        if not isinstance(frame, np.ndarray) or frame.size == 0 or frame.ndim not in (2, 3):
            raise EnrollmentValidationError("Ảnh mẫu không hợp lệ.")
        crop = crop_face(frame, result.selected.bbox)
        frame_hash = hashlib.sha256(crop.tobytes() + repr(crop.shape).encode("ascii")).digest()
        vector = np.asarray(result.embedding, dtype=np.float32)
        if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all():
            raise EnrollmentValidationError("Embedding sai định dạng hoặc chứa giá trị không hữu hạn.")
        model_identity = (getattr(result, "model_name", "buffalo_l"),
                          getattr(result, "model_version", "w600k_r50.onnx"))
        if not all(model_identity):
            raise EnrollmentValidationError("Không xác định được model đã tạo embedding.")
        if self.samples:
            first = self.samples[0]
            if vector.size != first.embedding.size:
                raise EnrollmentValidationError("Kích thước embedding giữa các mẫu không đồng nhất.")
            if model_identity != (first.model_name, first.model_version):
                raise EnrollmentValidationError("Các mẫu được tạo từ model khác nhau.")
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 0:
            raise EnrollmentValidationError("Embedding có chuẩn không hợp lệ.")
        vector = np.ascontiguousarray(vector / norm, dtype=np.float32)
        embedding_hash = hashlib.sha256(vector.tobytes()).digest()
        if frame_hash in self._frame_hashes or embedding_hash in self._embedding_hashes:
            raise EnrollmentValidationError("Ảnh hoặc embedding trùng mẫu đã nhận.")
        sample = EnrollmentSample(
            frame=frame.copy(), bbox=tuple(result.selected.bbox), embedding=vector.copy(),
            status=result.status, face_count=result.face_count,
            model_name=model_identity[0], model_version=model_identity[1],
        )
        self.samples.append(sample)
        self._frame_hashes.add(frame_hash)
        self._embedding_hashes.add(embedding_hash)
        return sample

    def retake_last(self):
        if not self.samples:
            return None
        sample = self.samples.pop()
        crop = crop_face(sample.frame, sample.bbox)
        self._frame_hashes.discard(hashlib.sha256(crop.tobytes() + repr(crop.shape).encode("ascii")).digest())
        self._embedding_hashes.discard(hashlib.sha256(np.ascontiguousarray(sample.embedding).tobytes()).digest())
        return sample


class EnrollmentService:
    """Save one person/profile and its four linked images and embeddings atomically."""

    def __init__(self, database_path=None):
        self.database_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
        self.image_directory = self.database_path.parent / "faces"
        self.image_path_root = PROJECT_ROOT if self.database_path.resolve() == DEFAULT_DATABASE_PATH.resolve() else self.database_path.parent

    def enroll_employee(self, person_data, employee_data, samples):
        from app.services.authorization_service import require_permission
        require_permission("employee.face.enroll")
        return self._enroll("employee", person_data, employee_data, samples)

    def enroll_student(self, person_data, student_data, samples):
        from app.services.authorization_service import require_permission
        require_permission("student.face.enroll")
        return self._enroll("student", person_data, student_data, samples)

    def _enroll(self, kind, person_data, profile_data, samples):
        person_data = dict(person_data)
        profile_data = dict(profile_data)
        validated = validate_samples(samples)
        self._validate_form(person_data, profile_data, kind)
        # Initialize only a missing/empty database from the existing schema. Existing
        # versioned databases are validated without being rewritten by this helper.
        initialize_database(self.database_path)
        self.image_directory.mkdir(parents=True, exist_ok=True)
        paths = []
        try:
            connection = connect(self.database_path)
            try:
                users = UserRepository(connection)
                faces = FaceRepository(connection)
                classes = ClassRepository(connection)
                with transaction(connection, immediate=True):
                    code = profile_data["employee_code" if kind == "employee" else "student_code"]
                    existing = (users.get_employee_by_code(code) if kind == "employee"
                                else users.get_student_by_code(code))
                    if existing is not None:
                        raise EnrollmentConflictError(f"Mã {code} đã được sử dụng; không ghi đè hồ sơ hiện có.")

                    department_id = None
                    class_record = None
                    if kind == "employee":
                        department_name = profile_data.pop("department_name", None)
                        if department_name:
                            department_id = next(
                                (row["department_id"] for row in users.list_departments()
                                 if row["name"] == department_name), None
                            )
                            if department_id is None:
                                raise EnrollmentConflictError("Phòng ban đã chọn không còn tồn tại hoặc không hoạt động.")
                        person_id, profile_id = users.create_employee_with_person(
                            Person(person_id=None, **person_data),
                            Employee(employee_id=None, person_id=0, employee_code=code,
                                     department_id=department_id,
                                     job_title=profile_data.get("job_title"),
                                     hire_date=profile_data.get("hire_date"),
                                     address=profile_data.get("address")),
                        )
                    else:
                        class_name = profile_data.pop("class_name", None)
                        academic_year = profile_data.pop("academic_year", None)
                        matches = [row for row in classes.list_classes(status="active")
                                   if row["class_name"] == class_name and row["academic_year"] == academic_year]
                        if len(matches) > 1:
                            raise EnrollmentValidationError("Có nhiều lớp trùng tên/năm học; không thể chọn an toàn.")
                        if not matches:
                            raise EnrollmentConflictError("Lớp đã chọn không còn hoạt động; hãy tải lại danh sách lớp.")
                        class_record = matches[0]
                        person_id, profile_id = users.create_student_with_person(
                            Person(person_id=None, **person_data),
                            Student(student_id=None, person_id=0, student_code=code,
                                    guardian_name=profile_data.get("guardian_name"),
                                    guardian_phone=profile_data.get("guardian_phone")),
                        )
                        classes.create_enrollment(Enrollment(
                            enrollment_id=None, student_id=profile_id,
                            class_id=class_record["class_id"], start_date=date.today().isoformat(),
                        ))

                    for index, (crop, vector, model_name, model_version) in enumerate(validated):
                        filename = f"{person_id}_{uuid.uuid4().hex}_{index + 1}.jpg"
                        absolute_path = self.image_directory / filename
                        ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        if not ok:
                            raise OSError(f"Không mã hóa được ảnh mẫu {index + 1}.")
                        paths.append(absolute_path)
                        absolute_path.write_bytes(encoded.tobytes())
                        relative_path = absolute_path.relative_to(self.image_path_root).as_posix()
                        image_id = faces.create_image(FaceImage(
                            image_id=None, person_id=person_id, image_path=relative_path,
                            capture_label=SAMPLE_LABELS[index],
                        ))
                        faces.create_embedding(FaceEmbedding(
                            embedding_id=None, person_id=person_id, image_id=image_id,
                            model_name=model_name, model_version=model_version,
                            dimension=int(vector.size), dtype="float32", vector_data=vector.tobytes(),
                        ))
                return {"person_id": person_id, "profile_id": profile_id, "dimension": validated[0][1].size}
            finally:
                connection.close()
        except Exception:
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    @staticmethod
    def _validate_form(person_data, profile_data, kind):
        required = ("full_name", "employee_code" if kind == "employee" else "student_code")
        values = [(person_data if name == "full_name" else profile_data).get(name) for name in required]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise EnrollmentValidationError("Mã và họ tên là thông tin bắt buộc.")
