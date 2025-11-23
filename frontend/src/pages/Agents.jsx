import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import {
  Play,
  Loader,
  Database,
  Target,
  Search,
  UserCheck,
  Mail,
  Terminal,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

/**
 * Agents page - premium UI that matches Dashboard styles while preserving existing logic.
 *
 * Key points:
 * - API endpoints and behavior unchanged.
 * - SSE, job polling, output preview, log modal, auto-reply controls preserved.
 * - Visual refresh: rounded-2xl cards, shadows, gradients, consistent spacing with Dashboard.
 */

export default function Agents() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState({}); // jobId -> {status, agent, logs: [], output,...}
  const [runningAgentId, setRunningAgentId] = useState(null);
  const [expandedJob, setExpandedJob] = useState(null); // job object for modal viewer
  const [emailAutoReplyRunning, setEmailAutoReplyRunning] = useState(false);
  const [showOutputPreview, setShowOutputPreview] = useState(null); // {agent, data}
  const [errorMsg, setErrorMsg] = useState(null);

  const navigate = useNavigate();
  const username = localStorage.getItem("username");
  const BASE_URL = "http://127.0.0.1:8000";

  const sseRefs = useRef({}); // jobId -> EventSource

  useEffect(() => {
    if (!username) {
      navigate("/auth");
      return;
    }

    let mounted = true;
    axios
      .get(`${BASE_URL}/agents/list`)
      .then((res) => {
        if (!mounted) return;
        setAgents(res.data.agents || []);
      })
      .catch((err) => {
        console.error("Failed to fetch agents", err);
        setErrorMsg("Failed to load agent list");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
      Object.values(sseRefs.current).forEach((es) => {
        try {
          es.close();
        } catch {}
      });
    };
  }, [username, navigate]);

  // Poll email_sender status every 2s (for toggle state)
  useEffect(() => {
    if (!username) return;
    let mounted = true;
    const poll = async () => {
      try {
        const res = await axios.get(`${BASE_URL}/agents/${username}/email_sender/status`);
        if (mounted && res.data && typeof res.data.running !== "undefined") {
          setEmailAutoReplyRunning(Boolean(res.data.running));
        }
      } catch (e) {
        if (mounted) setEmailAutoReplyRunning(false);
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [username]);

  // ---------- SSE log handling (unchanged endpoints) ----------
  const startSseForJob = (jobId) => {
    if (sseRefs.current[jobId]) return;

    const es = new EventSource(`${BASE_URL}/agents/${username}/stream/${jobId}`);
    sseRefs.current[jobId] = es;

    es.onmessage = (e) => {
      let line = (e.data || "").trim();
      if (!line || /^\s+$/.test(line)) return;

      setJobs((prev) => {
        const j = prev[jobId] || { logs: [] };
        return {
          ...prev,
          [jobId]: { ...j, logs: [...j.logs, line], status: j.status || "running", agent: j.agent || "" },
        };
      });
    };

    es.addEventListener("close", () => {
      try {
        es.close();
      } catch {}
      delete sseRefs.current[jobId];
    });

    es.onerror = () => {
      // ignore - connection will close when job completes on server
    };
  };

  // ---------- Run / Pipeline ----------
  const runAgent = async (agentName) => {
    try {
      setLoading(true);
      const res = await axios.post(`${BASE_URL}/agents/${username}/run/${agentName}`);
      const jobId = res.data.job_id;
      setJobs((prev) => ({ ...prev, [jobId]: { status: "queued", logs: [], agent: agentName } }));
      startSseForJob(jobId);
      setRunningAgentId(jobId);
      await pollUntilDone(jobId);
      await fetchOutputAndAttach(agentName, jobId);
    } catch (err) {
      console.error("Run agent failed", err);
      alert("Failed to enqueue agent.");
    } finally {
      setLoading(false);
      setRunningAgentId(null);
    }
  };

  const runPipeline = async () => {
    try {
      setLoading(true);
      const res = await axios.post(`${BASE_URL}/agents/${username}/run/pipeline`);
      const jobsOrdered = res.data.jobs || [];
      for (const j of jobsOrdered) {
        const jobId = j.job_id;
        const agentName = j.agent;
        setJobs((prev) => ({ ...prev, [jobId]: { status: "queued", logs: [], agent: agentName } }));
        startSseForJob(jobId);
        setRunningAgentId(jobId);
        await pollUntilDone(jobId);
        await fetchOutputAndAttach(agentName, jobId);
      }
      setRunningAgentId(null);
    } catch (err) {
      console.error("Pipeline failed", err);
      alert("Failed to enqueue pipeline.");
    } finally {
      setLoading(false);
    }
  };

  const pollUntilDone = async (jobId, interval = 1500) => {
    while (true) {
      try {
        const r = await axios.get(`${BASE_URL}/agents/${username}/job/${jobId}`);
        const status = r.data.status;
        if (status === "completed" || status === "failed") {
          setJobs((prev) => ({ ...prev, [jobId]: { ...(prev[jobId] || {}), status } }));
          return r.data;
        }
      } catch (err) {
        // ignore transient
      }
      await new Promise((res) => setTimeout(res, interval));
    }
  };

  // ---------- Output fetch ----------
  const fetchOutputAndAttach = async (agentName, jobId) => {
    // allow file flush
    await new Promise((r) => setTimeout(r, 700));
    try {
      const r = await axios.get(`${BASE_URL}/agents/${username}/output/${agentName}`);
      setJobs((prev) => {
        const j = prev[jobId] || { logs: [], status: "completed", agent: agentName };
        return { ...prev, [jobId]: { ...j, output: r.data.output } };
      });
    } catch (err) {
      setJobs((prev) => {
        const j = prev[jobId] || { logs: [], status: "completed", agent: agentName };
        return { ...prev, [jobId]: { ...j, output_error: "Output not available yet" } };
      });
    }
  };

  // ---------- Auto-reply start / stop ----------
  const startAutoReply = async () => {
    try {
      await axios.post(`${BASE_URL}/agents/${username}/email_sender/auto_reply/start`);
      setEmailAutoReplyRunning(true);
    } catch (err) {
      console.error("Start failed", err);
      alert("Failed to start auto-reply.");
    }
  };

  const stopAutoReply = async () => {
    try {
      await axios.post(`${BASE_URL}/agents/${username}/email_sender/stop`);
      setEmailAutoReplyRunning(false);
    } catch (err) {
      console.error("Stop failed", err);
      alert("Failed to send stop signal.");
    }
  };

  // ---------- Friendly UI mapping ----------
  const agentConfig = {
    enrichment_agent: {
      name: "Data Enrichment",
      description: "Enrich company data with AI-driven intelligence",
      icon: <Database className="w-6 h-6" />,
    },
    scoring_agent: {
      name: "Lead Scoring",
      description: "Score leads based on data intelligence",
      icon: <Target className="w-6 h-6" />,
    },
    employee_finder: {
      name: "Employee Finder",
      description: "Identify key people within target companies",
      icon: <Search className="w-6 h-6" />,
    },
    contact_finder: {
      name: "Contact Finder",
      description: "Verify and validate contact information",
      icon: <UserCheck className="w-6 h-6" />,
    },
    email_sender: {
      name: "Email Campaign",
      description: "Send personalized outreach emails at scale",
      icon: <Mail className="w-6 h-6" />,
    },
  };

  // ---------- UI helpers ----------
  const openLogModal = (job) => setExpandedJob(job);
  const closeLogModal = () => setExpandedJob(null);

  const openOutputPreview = (agentName, data) => setShowOutputPreview({ agent: agentName, data });
  const closeOutputPreview = () => setShowOutputPreview(null);

  // render status badge
  const statusBadge = (status) => {
    if (!status || status === "idle") return <span className="px-2 py-1 text-xs bg-slate-100 text-slate-700 rounded">Idle</span>;
    if (status === "queued") return <span className="px-2 py-1 text-xs bg-indigo-100 text-indigo-700 rounded">Queued</span>;
    if (status === "running") return <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Running</span>;
    if (status === "completed") return <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Completed</span>;
    if (status === "failed") return <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Failed</span>;
    return <span className="px-2 py-1 text-xs bg-slate-100 text-slate-700 rounded">{status}</span>;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-b from-white to-slate-50">
        <div className="text-center">
          <div className="inline-block w-16 h-16 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-5"></div>
          <h3 className="text-lg font-semibold text-slate-700">Loading agents...</h3>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-8 bg-slate-50">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-6 mb-8">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Agent Control Center</h1>
            <p className="mt-1 text-sm text-slate-500">Run agents, monitor logs, and control email auto-replies.</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/dashboard")}
              className="px-4 py-2 rounded-lg border bg-white text-slate-700 hover:shadow"
            >
              Back
            </button>

            <button
              onClick={runPipeline}
              disabled={!!runningAgentId}
              className="px-4 py-2 rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow hover:opacity-95 disabled:opacity-60"
            >
              Run Full Workflow
            </button>
          </div>
        </div>

        {/* grid of agent cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => {
            const cfg = agentConfig[agent] || { name: agent, description: "Custom Agent", icon: <Terminal className="w-6 h-6" /> };
            // find latest job for this agent
            const jobEntry = Object.values(jobs).reverse().find((j) => j.agent === agent) || null;
            const status = jobEntry ? jobEntry.status : "idle";
            const isRunning = status === "running" || status === "queued";
            return (
              <div key={agent} className="relative bg-white rounded-2xl shadow-lg border p-5 flex flex-col justify-between hover:shadow-xl transition">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="p-3 rounded-xl bg-indigo-50 text-indigo-600">{cfg.icon}</div>
                    <div>
                      <h3 className="text-lg font-semibold text-slate-900">{cfg.name}</h3>
                      <p className="mt-1 text-sm text-slate-500">{cfg.description}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <div>{statusBadge(status)}</div>
                    <div className="text-xs text-slate-400">{jobEntry ? `Last run` : "No runs yet"}</div>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      onClick={() => runAgent(agent)}
                      disabled={!!runningAgentId}
                      className="px-4 py-2 rounded-md bg-indigo-600 text-white text-sm shadow-sm disabled:opacity-60"
                    >
                      Run
                    </button>

                    <button
                      onClick={() => {
                        const j = Object.values(jobs).reverse().find((x) => x.agent === agent);
                        if (j) {
                          // open logs in modal
                          openLogModal(j);
                        } else {
                          alert("No runs yet for this agent.");
                        }
                      }}
                      className="px-3 py-2 rounded-md border text-sm"
                    >
                      Show Latest
                    </button>

                    {/* email_sender special controls */}
                    {agent === "email_sender" && (
                      <div className="ml-auto flex items-center gap-2">
                        <button
                          onClick={startAutoReply}
                          disabled={emailAutoReplyRunning}
                          className={`px-3 py-2 rounded-md text-sm font-medium ${!emailAutoReplyRunning ? "bg-green-600 text-white" : "bg-gray-100 text-gray-600"}`}
                        >
                          Start Auto-Reply
                        </button>

                        <button
                          onClick={stopAutoReply}
                          disabled={!emailAutoReplyRunning}
                          className={`px-3 py-2 rounded-md text-sm font-medium ${emailAutoReplyRunning ? "bg-red-600 text-white" : "bg-gray-100 text-gray-600"}`}
                        >
                          Stop Auto-Reply
                        </button>

                        <div className="text-sm text-slate-600 ml-2">
                          {emailAutoReplyRunning ? <span className="text-green-600">● Auto-Reply ON</span> : <span className="text-red-500">● Auto-Reply OFF</span>}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* If latest job has output, show a mini-preview + open button */}
                  {jobEntry && jobEntry.output && jobEntry.output.source && (
                    <div className="mt-4 border rounded-lg p-3 bg-slate-50">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs text-slate-600">Latest output available</div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openOutputPreview(agent, jobEntry.output)}
                            className="px-3 py-1 text-xs rounded-md border bg-white"
                          >
                            Preview
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* If latest job has an error message */}
                  {jobEntry && jobEntry.output_error && (
                    <div className="mt-3 text-xs text-red-600">Output not available yet</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Recent Jobs */}
        <div className="mt-10">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-lg font-semibold text-slate-800">Recent Jobs</h4>
            <div className="text-sm text-slate-500">Showing latest in current session</div>
          </div>

          <div className="space-y-3">
            {Object.entries(jobs)
              .reverse()
              .map(([jobId, j]) => (
                <div key={jobId} className="bg-white rounded-xl p-4 border shadow-sm flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="w-10">
                      <div className="rounded-md bg-indigo-50 w-10 h-10 flex items-center justify-center text-indigo-600 font-semibold">
                        {j.agent ? j.agent.charAt(0).toUpperCase() : "A"}
                      </div>
                    </div>

                    <div>
                      <div className="text-sm font-medium text-slate-900">{j.agent}</div>
                      <div className="text-xs text-slate-500">Job: {jobId}</div>
                      <div className="mt-2 text-xs text-slate-600">
                        <strong>Status:</strong> {j.status}
                        {j.status === "failed" ? " ⚠️" : ""}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => openLogModal({ id: jobId, ...j })}
                      className="px-3 py-1 rounded-md border bg-white text-sm"
                    >
                      View Logs
                    </button>

                    {j.output ? (
                      <button
                        onClick={() => openOutputPreview(j.agent, j.output)}
                        className="px-3 py-1 rounded-md bg-indigo-600 text-white text-sm"
                      >
                        Show Output
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* ---------- Log modal ---------- */}
      {expandedJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <div className="absolute inset-0 bg-black/40" onClick={closeLogModal} />
          <div className="relative w-full max-w-4xl bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">Logs — {expandedJob.agent || expandedJob.agent}</h3>
                <div className="text-xs text-slate-500">Job: {expandedJob.id || Object.keys(jobs).find(k => jobs[k] === expandedJob) || ""}</div>
              </div>
              <div>
                <button onClick={closeLogModal} className="px-3 py-1 rounded-md border">Close</button>
              </div>
            </div>

            <div className="p-4">
              <div className="rounded-md bg-slate-900 text-white font-mono text-xs p-4 max-h-[420px] overflow-auto">
                {expandedJob.logs && expandedJob.logs.length > 0 ? (
                  expandedJob.logs.map((L, i) => (
                    <div key={i} className="whitespace-pre-wrap mb-1">{L}</div>
                  ))
                ) : (
                  <div className="text-slate-400">No logs captured yet.</div>
                )}
              </div>

              {expandedJob.output && (
                <div className="mt-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium">Output preview</div>
                    <div className="text-xs text-slate-500">Source: {expandedJob.output.source || "file"}</div>
                  </div>
                  <pre className="text-xs bg-slate-50 p-3 rounded max-h-60 overflow-auto border">
                    {typeof expandedJob.output === "string"
                      ? expandedJob.output
                      : JSON.stringify(expandedJob.output, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ---------- Output preview drawer ---------- */}
      {showOutputPreview && (
        <div className="fixed right-6 bottom-6 z-40 w-[420px]">
          <div className="bg-white shadow-lg rounded-xl overflow-hidden border">
            <div className="flex items-center justify-between p-3 border-b">
              <div>
                <div className="text-sm font-semibold">Output — {showOutputPreview.agent}</div>
                <div className="text-xs text-slate-500">Quick campaign summary</div>
              </div>
              <div>
                <button onClick={closeOutputPreview} className="px-2 py-1 rounded-md border">Close</button>
              </div>
            </div>

            <div className="p-3 text-xs">
              {showOutputPreview.data ? (
                <>
                  {/* If campaign_summary shape present, show recipients summary */}
                  {showOutputPreview.data.sent !== undefined ? (
                    <div>
                      <div className="text-sm font-medium mb-2">Sent: {showOutputPreview.data.sent} • Failed: {showOutputPreview.data.failed}</div>
                      <div className="max-h-48 overflow-auto space-y-2">
                        {(showOutputPreview.data.recipients || []).map((r, idx) => (
                          <div key={idx} className="p-2 rounded-md bg-slate-50 border">
                            <div className="flex items-center justify-between">
                              <div className="text-sm font-medium">{r.name || r.email}</div>
                              <div className="text-xs text-slate-500">{r.sent ? "Sent" : "Failed"}</div>
                            </div>
                            <div className="text-xs text-slate-600 mt-1 line-clamp-3" dangerouslySetInnerHTML={{ __html: r.content_html || "" }} />
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <pre className="text-xs bg-slate-50 p-2 rounded">{JSON.stringify(showOutputPreview.data, null, 2)}</pre>
                  )}
                </>
              ) : (
                <div className="text-slate-500">No preview available</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* small error banner */}
      {errorMsg && (
        <div className="fixed left-6 bottom-6 z-50">
          <div className="bg-red-600 text-white px-4 py-2 rounded-md shadow">
            {errorMsg}
          </div>
        </div>
      )}
    </div>
  );
}
