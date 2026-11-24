/** @typedef {{id:number, title:string, payload:object, author:string}} BusinessCase */
/** @typedef {{id:number, case_id:number, status:'queued'|'running'|'complete'|'failed'}} Run */
/** @typedef {{id:number, run_id:number, digest:string, report:{summary:string, metrics:object, sections:Array}}} Evidence */
/** @typedef {{case_id:number, total_rows:number, received_rows:number, next_row:number|null, sealed_at:string|null, run_id:number|null, segments:Array<{start_row:number, row_count:number, created_at:string}>}} IntakeProgress */
