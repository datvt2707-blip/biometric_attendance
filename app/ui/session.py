"""In-memory session containing only claims returned by AuthenticationService."""
from app.services.authentication_service import AuthenticatedIdentity
from app.services.authorization_service import AuthorizationService, role_context


current = {"identity": None}


def establish(identity):
    if not isinstance(identity, AuthenticatedIdentity):
        raise PermissionError("Phiên chỉ nhận danh tính do dịch vụ xác thực phát hành.")
    if identity.account_id <= 0 or not identity.roles or not identity.permissions:
        raise PermissionError("Tài khoản chưa có quyền truy cập đã cấu hình.")
    current["identity"] = identity
    AuthorizationService.set_identity(identity)


def logout():
    current["identity"] = None
    AuthorizationService.clear()


def identity():
    value = current["identity"]
    if value is None:
        raise PermissionError("Cần đăng nhập để tiếp tục.")
    return value


def has_permission(permission_code):
    if not isinstance(permission_code, str) or not permission_code.strip():
        return False
    try:
        value = identity()
    except PermissionError:
        return False
    return any(item.get("permission_code") == permission_code for item in value.permissions)


def require_permission(permission_code):
    value = identity()
    if not has_permission(permission_code):
        raise PermissionError(f"Tài khoản không có quyền: {permission_code}.")
    return value


def role():
    return role_context(identity())
