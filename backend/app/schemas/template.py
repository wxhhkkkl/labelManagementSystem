"""T124：模板元素结构校验（实现 contracts/template-rendering.md 第 3~5 节）。

入库前就把不合契约的元素拦下。放在这里的价值是**两端一致**：
渲染器遇到未知类型会抛错（契约要求），如果等到打印时才发现，
那张标签已经废了；在这里拦下则管理员当场就能改。
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

ElementType = Literal["qrcode", "barcode", "text", "field", "date", "serial"]

ALIGNMENTS = ("left", "center", "right")
# 动态字段包括业务字段与服务端保存的首次打印日期、每日流水号。
FIELD_NAMES = (
    "product_name",
    "company_name",
    "code_value",
    "batch_no",
    "production_batch_no",
    "print_date",
    "serial_no",
)

# 纸张尺寸的合理上界（毫米）。打印机的物理极限远小于这个数，
# 但设成硬上限能拦住"把 60 看成 6000"这类手误。
MAX_PAPER_MM = 500


class TemplateElement(BaseModel):
    type: ElementType
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    # 顺时针旋转角度。x/y 始终是旋转后外接框的左上角。
    rotate: Literal[0, 90, 180, 270] = 0

    # 图形元素
    size: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    ec_level: Literal["L", "M", "Q", "H"] | None = None
    symbology: Literal["code128", "code39", "ean13"] | None = None
    show_text: bool | None = None

    # 文本 / 动态字段
    content: str | None = None
    field_name: str | None = None
    font_size: float | None = Field(default=None, gt=0)
    font_family: str | None = None
    bold: bool | None = None
    align: Literal["left", "center", "right"] | None = None
    multiline: bool | None = None
    date_source: Literal["print", "fixed"] = "print"
    date_format: Literal["YYYY-MM-DD", "YY-MM-DD", "YYYY/MM/DD", "YYYYMMDD", "YYYY年MM月DD日"] = (
        "YYYY-MM-DD"
    )
    prefix: str = Field(default="", max_length=64)
    suffix: str = Field(default="", max_length=64)
    serial_digits: int = Field(default=6, ge=1, le=12)

    @model_validator(mode="after")
    def _require_type_specific_attributes(self) -> "TemplateElement":
        if self.field_name is not None and self.field_name not in FIELD_NAMES:
            raise ValueError("未知的动态字段名")
        if self.type in ("date", "serial") and self.font_size is None:
            raise ValueError("日期或流水号元素必须提供 font_size")
        if self.type == "date" and self.date_source == "fixed":
            from datetime import date

            try:
                parsed = date.fromisoformat(self.content or "")
                if parsed.isoformat() != self.content:
                    raise ValueError("日期格式必须为 YYYY-MM-DD")
            except ValueError as exc:
                raise ValueError("固定日期必须为有效的 YYYY-MM-DD 日期") from exc
        if self.type == "qrcode" and self.size is None:
            raise ValueError("二维码元素必须提供 size")
        if self.type == "barcode" and (self.width is None or self.height is None):
            raise ValueError("条码元素必须提供 width 与 height")
        if self.type == "text":
            if self.content is None:
                raise ValueError("文本元素必须提供 content")
            if self.font_size is None:
                raise ValueError("文本元素必须提供 font_size")
        if self.type == "field":
            if self.field_name is None:
                raise ValueError("动态字段元素必须提供 field_name")
            if self.field_name not in FIELD_NAMES:
                raise ValueError(
                    f"未知的动态字段名 {self.field_name}，仅支持：{'、'.join(FIELD_NAMES)}"
                )
            if self.font_size is None:
                raise ValueError("动态字段元素必须提供 font_size")
        return self


class TemplateDoc(BaseModel):
    """一份模板版本的内容。"""

    paper_width_mm: float = Field(gt=0, le=MAX_PAPER_MM)
    paper_height_mm: float = Field(gt=0, le=MAX_PAPER_MM)
    elements: list[TemplateElement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _warn_on_out_of_paper_elements(self) -> "TemplateDoc":
        # 超出纸张不算错误——渲染端会裁剪（契约第 1 节要求"裁剪而非缩放"）。
        # 但一个元素整个落在纸外通常是坐标填错了，这里直接拦下。
        for index, el in enumerate(self.elements):
            if el.x >= self.paper_width_mm or el.y >= self.paper_height_mm:
                raise ValueError(f"第 {index + 1} 个元素的起点 ({el.x}, {el.y}) 已在纸张之外")
        return self


# ---------------------------------------------------------------- 请求模型


class TemplateCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    # 新建时可选地一并给出首个版本内容；不给则创建一个空白版本
    paper_width_mm: float | None = Field(default=None, gt=0, le=MAX_PAPER_MM)
    paper_height_mm: float | None = Field(default=None, gt=0, le=MAX_PAPER_MM)
    elements: list[TemplateElement] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    """修改模板 = 生成新版本（FR-033）。

    不允许只改名称——名称变更也走新版本，保证"历史版本内容冻结"这条规则
    没有例外可钻。
    """

    paper_width_mm: float = Field(gt=0, le=MAX_PAPER_MM)
    paper_height_mm: float = Field(gt=0, le=MAX_PAPER_MM)
    elements: list[TemplateElement] = Field(default_factory=list)


class TemplateVersionOut(BaseModel):
    id: int
    template_id: int
    version_no: int
    paper_width_mm: float
    paper_height_mm: float
    elements_json: dict
    frozen: bool


class TemplateOut(BaseModel):
    id: int
    code: str
    name: str
    status: str
    current_version_no: int | None = None
    version_count: int = 0


def to_document(paper_width_mm: float, paper_height_mm: float, elements: list) -> dict:
    """把请求体规整成入库用的 elements_json。

    存整份文档（含纸张尺寸）而不是只存元素数组——渲染器需要一次性拿到完整版面。

    这里是版面的唯一校验入口，所以把 pydantic 的 ValidationError 转成统一的
    ApiError：否则它会以 500 冒出去，而这个错误本质是"调用方传的模板不合法"（422）。
    """
    from app.core.errors import ApiError, ErrorCode

    try:
        doc = TemplateDoc(
            paper_width_mm=paper_width_mm, paper_height_mm=paper_height_mm, elements=elements
        )
    except ValidationError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, _first_message(exc)) from exc
    return doc.model_dump()


def _first_message(exc: ValidationError) -> str:
    """取第一条校验失败信息，去掉 pydantic 的前缀噪音。"""
    errors = exc.errors()
    if not errors:
        return "模板内容不合法"
    return str(errors[0].get("msg", "模板内容不合法")).removeprefix("Value error, ")
