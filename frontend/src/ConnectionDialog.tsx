import { useEffect, useState } from "react";
import { api } from "./api";
import { Dialog } from "./CompletionDialog";
import type {
  CompanyConnection,
  ConnectionMode,
  ConnectionStatus,
} from "./types";

const blank: CompanyConnection = {
  base_url: "",
  model: "",
  effort: null,
  api_key_env: "OPENAI_API_KEY",
  organization: null,
};

export default function ConnectionDialog({
  cancel,
  active,
}: {
  cancel: () => void;
  active: boolean;
}) {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [selected, setSelected] = useState<ConnectionMode>("personal");
  const [company, setCompany] = useState<CompanyConnection>(blank);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api<ConnectionStatus>("coach/connection")
      .then((value) => {
        if (cancelled) return;
        setStatus(value);
        setSelected(value.selected || value.recommendation);
        setCompany(value.company || blank);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const field = (key: keyof CompanyConnection, value: string | null) =>
    setCompany((previous) => ({ ...previous, [key]: value }));
  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await api("coach/connection", {
        selected,
        company: selected === "company" ? company : status?.company,
      });
      cancel();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog
      cancel={cancel}
      titleId="connection-title"
      closeLabel="Close connection settings"
    >
      <h2 id="connection-title">Coaching connection</h2>
      <p>
        This choice is saved on this computer. Your practice continues with
        either connection.
      </p>
      {!status && !error && <p role="status">Reading connection settings…</p>}
      {error && (
        <p role="alert" className="warning-text">
          {error}
        </p>
      )}
      {status && (
        <form
          className="connection-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          {!status.selected && (
            <p className="notice">{status.reason} Confirm your choice below.</p>
          )}
          <label>
            Connection
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value as ConnectionMode)}
            >
              <option value="personal">Personal ChatGPT</option>
              <option value="company">Company</option>
            </select>
          </label>
          {selected === "personal" ? (
            <p>
              Connect with your personal ChatGPT sign-in and included Codex
              allowance.
            </p>
          ) : (
            <>
              <p>Company settings are saved independently in Practice Room.</p>
              {status.detected ? (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setCompany(status.detected!)}
                >
                  Use detected settings
                </button>
              ) : null}
              <label>
                API base URL
                <input
                  type="url"
                  required
                  value={company.base_url}
                  placeholder="https://your-company-api.example/v1"
                  onChange={(e) => field("base_url", e.target.value)}
                />
              </label>
              <div className="connection-pair">
                <label>
                  Default model
                  <input
                    required
                    value={company.model}
                    onChange={(e) => field("model", e.target.value)}
                  />
                </label>
                <label>
                  Reasoning effort
                  <select
                    value={company.effort || ""}
                    onChange={(e) => field("effort", e.target.value || null)}
                  >
                    <option value="">Model default</option>
                    {[
                      "none",
                      "minimal",
                      "low",
                      "medium",
                      "high",
                      "xhigh",
                      "max",
                      "ultra",
                    ].map((effort) => (
                      <option key={effort} value={effort}>
                        {effort}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="connection-pair">
                <label>
                  Credential environment variable
                  <input
                    required
                    value={company.api_key_env}
                    onChange={(e) => field("api_key_env", e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label>
                  Organization ID (optional)
                  <input
                    value={company.organization || ""}
                    onChange={(e) =>
                      field("organization", e.target.value || null)
                    }
                    autoComplete="off"
                  />
                </label>
              </div>
              <small>
                Enter the variable name, not the API key. After setting it in
                your terminal, run <code>Start Study.cmd app --restart</code>{" "}
                from that terminal.
              </small>
              {status.company &&
                company.api_key_env === status.company.api_key_env && (
                  <p
                    role="status"
                    className={
                      status.credential_available ? "muted" : "warning-text"
                    }
                  >
                    {status.credential_available
                      ? "The saved credential variable is available to Practice Room."
                      : "The saved credential variable is unavailable. You can save settings and set it before connecting."}
                  </p>
                )}
              <small>Usage is managed by your organization.</small>
            </>
          )}
          {active && (
            <p role="status" className="warning-text">
              Wait for the reply to finish or Stop coach before changing
              connections.
            </p>
          )}
          <div className="button-row">
            <button type="button" className="secondary" onClick={cancel}>
              Cancel
            </button>
            <button
              type="submit"
              className="primary"
              disabled={saving || active}
            >
              {saving ? "Saving…" : "Save connection"}
            </button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
