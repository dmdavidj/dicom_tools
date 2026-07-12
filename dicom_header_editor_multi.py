# -*- coding: utf-8 -*-
"""
DICOM Header Viewer / Editor
============================
- DICOM(.dcm) 파일을 열어 헤더(Tag, VR, Name, Value)를 트리 형태로 조회
- Tag/이름/값으로 검색(필터링)
- 더블클릭 또는 [값 수정] 버튼으로 값 수정
- 원본 파일에 덮어쓰기 저장 / 다른 이름으로 저장
- Sequence(SQ) 항목도 펼쳐서 조회 가능 (수정은 단순 값 항목만 지원)

필요 패키지:
    pip install pydicom

실행:
    python dicom_header_editor.py
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import pydicom
    from pydicom.dataset import Dataset
    from pydicom.dataelem import DataElement
    from pydicom.multival import MultiValue
except ImportError:
    raise SystemExit("pydicom이 설치되어 있지 않습니다.  ->  pip install pydicom")


# 값이 너무 길면 목록에 표시할 때 잘라서 보여줌
MAX_DISPLAY_LEN = 120


def format_value(elem: DataElement) -> str:
    """트리에 표시할 값 문자열 생성"""
    if elem.VR == "SQ":
        return f"<Sequence: {len(elem.value)} item(s)>"
    if elem.VR in ("OB", "OW", "OF", "OD", "OL", "UN") and isinstance(elem.value, bytes):
        return f"<Binary data: {len(elem.value)} bytes>"
    try:
        v = elem.value
        if isinstance(v, MultiValue):
            s = "\\".join(str(x) for x in v)
        else:
            s = str(v)
    except Exception:
        s = "<표시 불가>"
    if len(s) > MAX_DISPLAY_LEN:
        s = s[:MAX_DISPLAY_LEN] + " ..."
    return s


class DicomHeaderEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DICOM Header Viewer / Editor")
        self.geometry("1100x700")

        self.ds = None                # 현재 열려 있는 pydicom Dataset
        self.file_path = None         # 현재 파일 경로
        self.modified = False         # 수정 여부
        self.item_map = {}            # treeview item id -> (dataset, tag) 매핑

        self._build_ui()
        self._update_title()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 상단 툴바 ----
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="DICOM 열기", command=self.open_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="저장 (덮어쓰기)", command=self.save_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="다른 이름으로 저장", command=self.save_file_as).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(toolbar, text="검색:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_tree())
        ttk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="초기화",
                   command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="다중 검색/수정",
                   command=self.open_batch_edit).pack(side=tk.LEFT, padx=2)

        # ---- 중앙 트리뷰 ----
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        columns = ("tag", "vr", "name", "value")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=30, stretch=False)
        self.tree.heading("tag", text="Tag")
        self.tree.column("tag", width=110, stretch=False)
        self.tree.heading("vr", text="VR")
        self.tree.column("vr", width=45, stretch=False)
        self.tree.heading("name", text="Name")
        self.tree.column("name", width=280)
        self.tree.heading("value", text="Value")
        self.tree.column("value", width=550)

        ysb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=ysb.set, xscroll=xsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ---- 하단 편집 패널 ----
        edit_frame = ttk.LabelFrame(self, text="선택 항목 편집", padding=8)
        edit_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        ttk.Label(edit_frame, text="Tag:").grid(row=0, column=0, sticky="w")
        self.sel_tag_var = tk.StringVar()
        ttk.Label(edit_frame, textvariable=self.sel_tag_var, width=14).grid(row=0, column=1, sticky="w")

        ttk.Label(edit_frame, text="Name:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.sel_name_var = tk.StringVar()
        ttk.Label(edit_frame, textvariable=self.sel_name_var, width=35).grid(row=0, column=3, sticky="w")

        ttk.Label(edit_frame, text="VR:").grid(row=0, column=4, sticky="w", padx=(10, 0))
        self.sel_vr_var = tk.StringVar()
        ttk.Label(edit_frame, textvariable=self.sel_vr_var, width=5).grid(row=0, column=5, sticky="w")

        ttk.Label(edit_frame, text="Value:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.value_text = tk.Text(edit_frame, height=3, width=100)
        self.value_text.grid(row=1, column=1, columnspan=5, sticky="ew", pady=(6, 0))
        edit_frame.columnconfigure(3, weight=1)

        btns = ttk.Frame(edit_frame)
        btns.grid(row=2, column=1, columnspan=5, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="값 수정 적용", command=self.apply_edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="선택 항목 삭제", command=self.delete_selected).pack(side=tk.LEFT, padx=2)

        # ---- 상태바 ----
        self.status_var = tk.StringVar(value="파일을 열어주세요.")
        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor="w", padding=3).pack(side=tk.BOTTOM, fill=tk.X)

    def _update_title(self):
        name = os.path.basename(self.file_path) if self.file_path else "(파일 없음)"
        mark = " *" if self.modified else ""
        self.title(f"DICOM Header Editor - {name}{mark}")

    # ------------------------------------------------------------- 파일 I/O
    def open_file(self):
        if self.modified and not messagebox.askyesno(
                "확인", "저장하지 않은 변경사항이 있습니다. 무시하고 새 파일을 여시겠습니까?"):
            return
        path = filedialog.askopenfilename(
            title="DICOM 파일 선택",
            filetypes=[("DICOM files", "*.dcm *.DCM *.dicom"), ("All files", "*.*")])
        if not path:
            return
        try:
            ds = pydicom.dcmread(path, force=True)
        except Exception as e:
            messagebox.showerror("오류", f"DICOM 파일을 읽을 수 없습니다.\n{e}")
            return
        self.ds = ds
        self.file_path = path
        self.modified = False
        self.refresh_tree()
        self.status_var.set(f"열림: {path}  (요소 {len(ds)}개)")
        self._update_title()

    def save_file(self):
        if self.ds is None:
            messagebox.showwarning("경고", "열려 있는 파일이 없습니다.")
            return
        if not messagebox.askyesno("확인", "원본 파일에 덮어쓰기 저장하시겠습니까?"):
            return
        self._write(self.file_path)

    def save_file_as(self):
        if self.ds is None:
            messagebox.showwarning("경고", "열려 있는 파일이 없습니다.")
            return
        path = filedialog.asksaveasfilename(
            title="다른 이름으로 저장", defaultextension=".dcm",
            filetypes=[("DICOM files", "*.dcm"), ("All files", "*.*")])
        if not path:
            return
        self._write(path)
        self.file_path = path

    def _write(self, path):
        try:
            self.ds.save_as(path, write_like_original=True)
        except Exception as e:
            messagebox.showerror("오류", f"저장 실패:\n{e}")
            return
        self.modified = False
        self._update_title()
        self.status_var.set(f"저장 완료: {path}")

    # ------------------------------------------------------------- 트리 표시
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.item_map.clear()
        if self.ds is None:
            return
        keyword = self.search_var.get().strip().lower()

        # file_meta(그룹 0002)도 함께 표시
        if getattr(self.ds, "file_meta", None):
            meta_node = self.tree.insert("", tk.END, text="",
                                         values=("", "", "--- File Meta (Group 0002) ---", ""),
                                         open=True)
            self._insert_dataset(self.ds.file_meta, meta_node, keyword)

        self._insert_dataset(self.ds, "", keyword)

    def _insert_dataset(self, ds: Dataset, parent, keyword):
        for elem in ds:
            tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            name = elem.name or ""
            val_str = format_value(elem)

            if keyword:
                haystack = f"{tag_str} {name} {elem.keyword or ''} {val_str}".lower()
                match = keyword in haystack
            else:
                match = True

            if elem.VR == "SQ":
                # 시퀀스: 자식 중 매칭되는 게 있으면 부모도 표시
                node = self.tree.insert(parent, tk.END, text="",
                                        values=(tag_str, elem.VR, name, val_str), open=bool(keyword))
                self.item_map[node] = (ds, elem.tag)
                child_shown = False
                for i, item_ds in enumerate(elem.value):
                    item_node = self.tree.insert(node, tk.END, text="",
                                                 values=("", "", f"Item {i + 1}", ""), open=bool(keyword))
                    before = len(self.tree.get_children(item_node))
                    self._insert_dataset(item_ds, item_node, keyword)
                    after = len(self.tree.get_children(item_node))
                    if keyword and after == before:
                        self.tree.delete(item_node)
                    else:
                        child_shown = child_shown or (after > before) or not keyword
                if keyword and not match and not child_shown:
                    self.tree.delete(node)
            else:
                if match:
                    node = self.tree.insert(parent, tk.END, text="",
                                            values=(tag_str, elem.VR, name, val_str))
                    self.item_map[node] = (ds, elem.tag)

    # ------------------------------------------------------------- 선택/편집
    def _get_selected_element(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        info = self.item_map.get(sel[0])
        if info is None:
            return None, None
        ds, tag = info
        if tag not in ds:
            return None, None
        return ds, ds[tag]

    def _on_select(self, event=None):
        ds, elem = self._get_selected_element()
        self.value_text.delete("1.0", tk.END)
        if elem is None:
            self.sel_tag_var.set("")
            self.sel_name_var.set("")
            self.sel_vr_var.set("")
            return
        self.sel_tag_var.set(f"({elem.tag.group:04X},{elem.tag.element:04X})")
        self.sel_name_var.set(elem.name or "")
        self.sel_vr_var.set(elem.VR)
        if elem.VR == "SQ":
            self.value_text.insert("1.0", "<Sequence는 직접 수정할 수 없습니다>")
        elif isinstance(elem.value, bytes):
            self.value_text.insert("1.0", f"<Binary {len(elem.value)} bytes - 수정 불가>")
        else:
            v = elem.value
            if isinstance(v, MultiValue):
                self.value_text.insert("1.0", "\\".join(str(x) for x in v))
            else:
                self.value_text.insert("1.0", "" if v is None else str(v))

    def edit_selected(self):
        """더블클릭 시 편집 패널로 포커스 이동"""
        self._on_select()
        self.value_text.focus_set()

    def apply_edit(self):
        ds, elem = self._get_selected_element()
        if elem is None:
            messagebox.showwarning("경고", "수정할 항목을 선택하세요.")
            return
        if elem.VR == "SQ":
            messagebox.showwarning("경고", "Sequence 항목은 직접 수정할 수 없습니다.\n하위 항목을 선택해서 수정하세요.")
            return
        if isinstance(elem.value, bytes) and elem.VR in ("OB", "OW", "OF", "OD", "OL", "UN"):
            messagebox.showwarning("경고", "바이너리(픽셀 등) 데이터는 이 프로그램에서 수정할 수 없습니다.")
            return

        new_text = self.value_text.get("1.0", tk.END).strip()
        try:
            new_value = self._convert_value(elem, new_text)
            ds[elem.tag].value = new_value
        except Exception as e:
            messagebox.showerror("오류", f"값을 적용할 수 없습니다 (VR={elem.VR}):\n{e}")
            return

        self.modified = True
        self._update_title()
        self.refresh_tree()
        self.status_var.set(f"수정됨: {elem.name} = {new_text}")

    @staticmethod
    def _convert_value(elem: DataElement, text: str):
        """VR에 맞게 문자열을 적절한 타입으로 변환. '\\'로 다중값 지원"""
        parts = text.split("\\") if "\\" in text else [text]

        int_vrs = {"US", "SS", "UL", "SL", "IS", "UV", "SV"}
        float_vrs = {"FL", "FD", "DS"}

        def conv(p):
            p = p.strip()
            if elem.VR in int_vrs:
                return int(p)
            if elem.VR in float_vrs:
                return float(p)
            return p  # 문자열 계열 VR

        values = [conv(p) for p in parts]
        return values if len(values) > 1 else values[0]

    # --------------------------------------------------------- 다중 검색/수정
    def find_elements(self, keyword: str):
        """키워드에 매칭되는 (dataset, tag) 목록을 재귀적으로 수집 (SQ 내부 포함)"""
        keyword = keyword.strip().lower()
        results = []
        if not keyword or self.ds is None:
            return results

        def walk(ds):
            for elem in ds:
                tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
                kw_name = elem.keyword or ""  # 예: PatientName
                if elem.VR == "SQ":
                    for item_ds in elem.value:
                        walk(item_ds)  # Sequence 자체는 수정 대상 아님, 내부만 탐색
                else:
                    haystack = (f"{tag_str} {elem.name or ''} {kw_name} "
                                f"{format_value(elem)}").lower()
                    if keyword in haystack:
                        results.append((ds, elem.tag))

        if getattr(self.ds, "file_meta", None):
            walk(self.ds.file_meta)
        walk(self.ds)
        return results

    def open_batch_edit(self):
        if self.ds is None:
            messagebox.showwarning("경고", "먼저 DICOM 파일을 열어주세요.")
            return
        BatchEditDialog(self)

    def apply_batch_edits(self, edits):
        """edits: [(ds, tag, new_text), ...] 를 한 번에 적용. 성공/실패 건수 반환"""
        ok, fail, errors = 0, 0, []
        for ds, tag, new_text in edits:
            if tag not in ds:
                fail += 1
                errors.append(f"{tag}: 항목이 존재하지 않음")
                continue
            elem = ds[tag]
            try:
                ds[tag].value = self._convert_value(elem, new_text)
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"{elem.name} {tag}: {e}")
        if ok:
            self.modified = True
            self._update_title()
            self.refresh_tree()
        self.status_var.set(f"일괄 수정: 성공 {ok}건, 실패 {fail}건")
        return ok, fail, errors

    def delete_selected(self):
        ds, elem = self._get_selected_element()
        if elem is None:
            messagebox.showwarning("경고", "삭제할 항목을 선택하세요.")
            return
        if not messagebox.askyesno("확인", f"{elem.name} {self.sel_tag_var.get()} 항목을 삭제하시겠습니까?"):
            return
        del ds[elem.tag]
        self.modified = True
        self._update_title()
        self.refresh_tree()
        self.status_var.set(f"삭제됨: {elem.name}")


class BatchEditDialog(tk.Toplevel):
    """
    다중 검색 + 일괄 수정 다이얼로그
    - 검색어를 쉼표(,)로 여러 개 입력  예)  PatientName, PatientID, 0008,0060
      * 참고: 태그 번호로 검색할 때 (0008,0060) 형태의 쉼표는 괄호 안에 있으므로 분리되지 않음
    - 검색어별로 매칭된 항목이 번호와 함께 표시됨
    - 각 행의 '새 값' 칸에 값을 입력한 항목만 일괄 적용됨 (빈 칸은 건너뜀)
    """

    def __init__(self, master: "DicomHeaderEditor"):
        super().__init__(master)
        self.master_app = master
        self.title("다중 검색 / 일괄 수정")
        self.geometry("950x600")
        self.transient(master)
        self.grab_set()

        self.rows = []  # [(ds, tag, entry_widget), ...]

        # ---- 검색어 입력 ----
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="검색어 (쉼표로 구분):").pack(side=tk.LEFT)
        self.kw_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.kw_var, width=60)
        entry.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda e: self.do_search())
        ttk.Button(top, text="검색", command=self.do_search).pack(side=tk.LEFT)

        hint = ttk.Label(self, foreground="gray",
                         text="예)  PatientName, PatientID, StudyDate      "
                              "태그로 검색:  (0010,0010), (0008,0060)")
        hint.pack(fill=tk.X, padx=10)

        # ---- 결과 목록 (스크롤 가능) ----
        result_frame = ttk.LabelFrame(self, text="검색 결과 - '새 값'을 입력한 항목만 수정됩니다", padding=4)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        canvas = tk.Canvas(result_frame, highlightthickness=0)
        ysb = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ysb.set)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = ttk.Frame(canvas)
        self.inner_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(self.inner_id, width=e.width))
        # 마우스 휠 스크롤
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # ---- 하단 버튼 ----
        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill=tk.X)
        self.count_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.count_var).pack(side=tk.LEFT)
        ttk.Button(bottom, text="일괄 적용", command=self.apply_all).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="닫기", command=self.close).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.close)

    # 쉼표 분리 시 괄호 안의 쉼표( 태그 표기 (0010,0010) )는 보호
    @staticmethod
    def split_keywords(text: str):
        keywords, buf, depth = [], "", 0
        for ch in text:
            if ch == "(":
                depth += 1
                buf += ch
            elif ch == ")":
                depth = max(0, depth - 1)
                buf += ch
            elif ch == "," and depth == 0:
                if buf.strip():
                    keywords.append(buf.strip())
                buf = ""
            else:
                buf += ch
        if buf.strip():
            keywords.append(buf.strip())
        return keywords

    def do_search(self):
        # 기존 결과 지우기
        for w in self.inner.winfo_children():
            w.destroy()
        self.rows.clear()

        keywords = self.split_keywords(self.kw_var.get())
        if not keywords:
            self.count_var.set("검색어를 입력하세요.")
            return

        # 헤더 행
        header = ttk.Frame(self.inner)
        header.pack(fill=tk.X, pady=(0, 2))
        for text, w in (("No.", 5), ("검색어", 14), ("Tag", 13), ("Name", 26),
                        ("현재 값", 28), ("새 값", 25)):
            ttk.Label(header, text=text, width=w,
                      font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=2)

        seen = set()   # 같은 항목이 여러 검색어에 중복 매칭될 때 한 번만 표시
        no = 0
        for kw in keywords:
            matches = self.master_app.find_elements(kw)
            if not matches:
                row = ttk.Frame(self.inner)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text="-", width=5).pack(side=tk.LEFT, padx=2)
                ttk.Label(row, text=kw, width=14).pack(side=tk.LEFT, padx=2)
                ttk.Label(row, text="(매칭되는 항목 없음)",
                          foreground="red").pack(side=tk.LEFT, padx=2)
                continue
            for ds, tag in matches:
                key = (id(ds), tag)
                if key in seen:
                    continue
                seen.add(key)
                elem = ds[tag]
                if elem.VR == "SQ" or (isinstance(elem.value, bytes)
                                       and elem.VR in ("OB", "OW", "OF", "OD", "OL", "UN")):
                    continue  # 수정 불가 항목 제외
                no += 1
                row = ttk.Frame(self.inner)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=str(no), width=5).pack(side=tk.LEFT, padx=2)
                ttk.Label(row, text=kw, width=14).pack(side=tk.LEFT, padx=2)
                ttk.Label(row, text=f"({tag.group:04X},{tag.element:04X})",
                          width=13).pack(side=tk.LEFT, padx=2)
                ttk.Label(row, text=(elem.name or "")[:26], width=26).pack(side=tk.LEFT, padx=2)
                cur = format_value(elem)
                ttk.Label(row, text=cur[:28], width=28).pack(side=tk.LEFT, padx=2)
                ent = ttk.Entry(row, width=25)
                ent.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
                self.rows.append((ds, tag, ent))

        self.count_var.set(f"매칭된 항목: {no}개")

    def apply_all(self):
        edits = []
        for ds, tag, ent in self.rows:
            new_text = ent.get().strip()
            if new_text:  # 빈 칸은 수정하지 않음
                edits.append((ds, tag, new_text))
        if not edits:
            messagebox.showwarning("경고", "새 값이 입력된 항목이 없습니다.", parent=self)
            return
        if not messagebox.askyesno("확인", f"{len(edits)}개 항목을 일괄 수정하시겠습니까?", parent=self):
            return
        ok, fail, errors = self.master_app.apply_batch_edits(edits)
        msg = f"성공: {ok}건, 실패: {fail}건"
        if errors:
            msg += "\n\n[실패 내역]\n" + "\n".join(errors[:10])
        messagebox.showinfo("일괄 수정 결과", msg, parent=self)
        self.do_search()  # 수정된 현재 값으로 목록 갱신

    def close(self):
        self.grab_release()
        self.destroy()


if __name__ == "__main__":
    app = DicomHeaderEditor()
    app.mainloop()
