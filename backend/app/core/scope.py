"""T029：组织数据隔离（research.md R7 / FR-006 / FR-007）。

所有列表与详情查询 MUST 经由此处注入过滤条件，MUST NOT 在业务代码里各写一套。
单对象访问同样 MUST 校验归属，不能只依赖列表过滤。

越权一律返回 403 FORBIDDEN_SCOPE，并由调用方写 AuditLog(result='denied')。
"""


from app.core.deps import HQ_ADMIN, SUB_ADMIN
from app.core.errors import ApiError, ErrorCode
from app.models.user import User


class Scope:
    """登录用户的可见范围。

    hq_admin  -> 无过滤（scope_company_id 为 None）
    其他角色   -> 强制限定在其所属公司
    """

    def __init__(self, user: User) -> None:
        self.user = user

    @property
    def is_hq(self) -> bool:
        return self.user.role == HQ_ADMIN

    @property
    def scope_company_id(self) -> int | None:
        """强制过滤用的公司 ID；None 表示不过滤。"""
        if self.is_hq:
            return None
        if self.user.company_id is None:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "账号未关联企业，无法查询企业数据")
        return self.user.company_id

    def apply_company_filter(self, stmt, column):
        """把组织过滤条件加到查询上。"""
        scope_id = self.scope_company_id
        if scope_id is None:
            return stmt
        return stmt.where(column == scope_id)

    def assert_can_access_company(self, company_id: int | None) -> None:
        """访问某公司的数据是否有权限。"""
        scope_id = self.scope_company_id
        if scope_id is None:
            return
        if company_id != scope_id:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权访问其他公司的数据")

    def assert_can_administer_company(self, company_id: int) -> None:
        """是否有权管理某公司（创建/编辑其工位与账号）。"""
        if self.is_hq:
            return
        if self.user.role != SUB_ADMIN:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权管理公司信息")
        if self.user.company_id != company_id:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权管理其他公司")

    def assert_role_assignable(self, role: str) -> None:
        """是否能创建/修改目标角色的账号（FR-004）。

        子公司管理员只能管理本公司操作员账号，不得创建 sub_admin 及以上角色。
        """
        if self.is_hq:
            return
        if self.user.role != SUB_ADMIN:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权管理账号")
        if role != "operator":
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权创建或修改管理员账号")

    def resolve_target_company(self, requested_company_id: int | None) -> int | None:
        """确定新建对象应归属的公司。

        非总部角色 MUST NOT 通过传入 company_id 越权；一律落到自己所属公司。
        """
        if self.is_hq:
            return requested_company_id
        if requested_company_id is not None and requested_company_id != self.user.company_id:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权在其他公司下创建数据")
        return self.user.company_id


def get_scope(user: User) -> Scope:
    return Scope(user)
