export type Fact = { value: string; quote: string; line_ids: string[] };
export type Employment = {
  employer: Fact | null;
  role: Fact | null;
  start: Fact | null;
  end: Fact | null;
};
export type Education = {
  institution: Fact | null;
  degree: Fact | null;
  graduation: Fact | null;
};
export type Line = {
  id: string;
  page: number;
  text: string;
  method: "text" | "ocr";
  bbox: number[] | null;
};
export type RecordResult = {
  id: string;
  created_at: string;
  expires_at: string;
  result: {
    schema_version: string;
    provider: "local" | "openai";
    model: string | null;
    prompt_version: string;
    review_required: true;
    fields: {
      name: Fact | null;
      skills: Fact[];
      employment: Employment[];
      education: Education[];
    };
    experience: {
      lower_months: number;
      upper_months: number;
      lower_years: number;
      upper_years: number;
      dated_roles: number;
      excluded_roles: number;
      as_of: string;
      policy: string;
    };
    document: {
      lines: Line[];
      page_count: number;
      ocr_pages: number[];
      warnings: string[];
    };
    warnings: string[];
    timings_ms: { [key: string]: number };
  };
};
export type HistoryItem = {
  id: string;
  name: string | null;
  created_at: string;
  provider: string;
  warning_count: number;
};
export type Config = {
  provider: "local" | "openai";
  model: string | null;
  max_upload_bytes: number;
  max_pages: number;
  retention_hours: number;
  schema_version: string;
};
