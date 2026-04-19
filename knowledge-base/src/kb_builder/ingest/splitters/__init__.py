"""三个 splitter 共用的入口，直接从 submodule 再导出。"""

from kb_builder.ingest.splitters.interview_splitter import split_interview
from kb_builder.ingest.splitters.jd_splitter import split_jd
from kb_builder.ingest.splitters.user_splitter import split_user_doc

__all__ = ["split_jd", "split_interview", "split_user_doc"]
