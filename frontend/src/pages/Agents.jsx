import React, { useState, useEffect } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import {
  Cpu,
  Play,
  Loader,
  CheckCircle,
  XCircle,
  ArrowLeft,
  Zap,
  Database,
  Target,
  Search,
  UserCheck,
  Mail,
  Activity,
  AlertTriangle,
  RefreshCw,
  Sparkles,
  Clock,
  Terminal,
  ChevronDown,
  ChevronUp,
  FileText,
} from "lucide-react";

export default function Agents() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningAgents, setRunningAgents] = useState({});
  const [logs, setLogs] = useState({});
  const [results, setResults] = useState({});
  const [expandedAgent, setExpandedAgent] = useState(null);
  const navigate = useNavigate();

  const username = localStorage.getItem("username");
  const BASE_URL = "http://127.0.0.1:8000";

  useEffect(() => {
    if (!username) {
      navigate("/auth");
      return;
    }

    axios
      .get(`${BASE_URL}/agents/list`)
      .then((res) => {
        setAgents(res.data.agents || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [username, navigate]);

  const agentSteps = {
    enrichment_agent: [
      "Scraping company's website",
      "Searching DuckDuckGo for news and signals",
      "Structuring output data",
    ],
    scoring_agent: [
      "Loading Sentence Transformers",
      "Performing semantic matching",
      "Assigning lead scores",
    ],
    employee_finder: [
      "Scraping web sources",
      "Gathering employee details",
      "Filtering key decision makers",
    ],
    contact_finder: [
      "Generating email patterns",
      "Verifying each email",
      "Assigning confidence scores",
    ],
    email_sender: [
      "Authenticating Gmail API",
      "Sending emails in batch",
      "Tracking responses and auto-replying",
    ],
  };

  const runAgent = async (agentName) => {
    setRunningAgents((prev) => ({ ...prev, [agentName]: true }));
    setLogs((prev) => ({ ...prev, [agentName]: [] }));
    setResults((prev) => ({ ...prev, [agentName]: null }));

    try {
      await axios.post(`${BASE_URL}/agents/${username}/run/${agentName}?background=true`);

      // Simulate logs streaming
      const steps = agentSteps[agentName] || ["Running agent tasks..."];
      steps.forEach((step, index) => {
        setTimeout(() => {
          setLogs((prev) => ({
            ...prev,
            [agentName]: [...(prev[agentName] || []), `🟢 ${step}`],
          }));
        }, 1500 * (index + 1));
      });

      // Fetch final output after delay
      setTimeout(async () => {
        try {
          const res = await axios.get(`${BASE_URL}/agents/${username}/output/${agentName}`);
          setResults((prev) => ({
            ...prev,
            [agentName]: { ok: true, data: res.data.output },
          }));
        } catch {
          setResults((prev) => ({
            ...prev,
            [agentName]: { ok: false, error: "Output not available" },
          }));
        }
        setRunningAgents((prev) => ({ ...prev, [agentName]: false }));
      }, 1500 * (steps.length + 1));
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [agentName]: { ok: false, error: "Failed to start agent" },
      }));
      setRunningAgents((prev) => ({ ...prev, [agentName]: false }));
    }
  };

  const agentConfig = {
    enrichment_agent: {
      name: "Data Enrichment",
      description: "Enrich company data with AI-driven intelligence",
      icon: <Database className="w-6 h-6" />,
      gradient: "from-blue-500 to-blue-600",
    },
    scoring_agent: {
      name: "Lead Scoring",
      description: "Score leads based on data intelligence",
      icon: <Target className="w-6 h-6" />,
      gradient: "from-purple-500 to-purple-600",
    },
    employee_finder: {
      name: "Employee Finder",
      description: "Identify key people within target companies",
      icon: <Search className="w-6 h-6" />,
      gradient: "from-green-500 to-green-600",
    },
    contact_finder: {
      name: "Contact Finder",
      description: "Verify and validate contact information",
      icon: <UserCheck className="w-6 h-6" />,
      gradient: "from-orange-500 to-orange-600",
    },
    email_sender: {
      name: "Email Campaign",
      description: "Send personalized outreach emails at scale",
      icon: <Mail className="w-6 h-6" />,
      gradient: "from-indigo-500 to-indigo-600",
    },
  };

  if (loading)
    return (
      <div className="flex justify-center items-center h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <div className="text-center">
          <div className="inline-block w-16 h-16 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
          <p className="text-gray-600 text-lg font-medium">Loading agents...</p>
        </div>
      </div>
    );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-8">
      {/* Header */}
      <div className="bg-white rounded-2xl shadow-lg p-6 mb-8 border border-gray-100 flex justify-between items-center">
        <div className="flex items-center space-x-3">
          <div className="bg-gradient-to-br from-indigo-600 to-purple-600 p-3 rounded-xl shadow-lg">
            <Cpu className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">AI Agent Control Center</h1>
            <p className="text-gray-600 text-sm">Execute, monitor, and analyze agent outputs</p>
          </div>
        </div>
        <button
          onClick={() => navigate("/dashboard")}
          className="inline-flex items-center px-5 py-2.5 bg-white border-2 border-gray-200 rounded-lg text-gray-700 hover:border-indigo-400 hover:text-indigo-600 transition-all font-medium text-sm shadow-sm"
        >
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Dashboard
        </button>
      </div>

      {/* Agent Cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => {
          const config = agentConfig[agent] || {
            name: agent,
            description: "Custom AI Agent",
            icon: <Activity className="w-6 h-6" />,
            gradient: "from-gray-500 to-gray-600",
          };

          const isRunning = runningAgents[agent];
          const agentLogs = logs[agent] || [];
          const result = results[agent];

          return (
            <div
              key={agent}
              className={`bg-white rounded-2xl shadow-lg border border-gray-200 transition-all overflow-hidden ${
                expandedAgent === agent ? "ring-4 ring-indigo-100" : ""
              }`}
            >
              {/* Header */}
              <div className={`bg-gradient-to-r ${config.gradient} p-5 text-white`}>
                <div className="flex justify-between items-center">
                  <div className="flex items-center space-x-3">
                    <div className="bg-white/20 p-2 rounded-lg">{config.icon}</div>
                    <h3 className="text-xl font-semibold">{config.name}</h3>
                  </div>
                  {isRunning ? (
                    <Loader className="w-5 h-5 animate-spin text-white" />
                  ) : result?.ok ? (
                    <CheckCircle className="w-5 h-5 text-green-300" />
                  ) : (
                    <Play className="w-5 h-5 opacity-70" />
                  )}
                </div>
              </div>

              {/* Body */}
              <div className="p-5 space-y-4">
                <p className="text-sm text-gray-700">{config.description}</p>

                {/* Run Button */}
                {!isRunning && (
                  <button
                    onClick={() => runAgent(agent)}
                    className={`w-full inline-flex items-center justify-center px-4 py-2 bg-gradient-to-r ${config.gradient} text-white rounded-lg font-semibold shadow-md hover:shadow-lg`}
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Run Agent
                  </button>
                )}

                {/* Logs Section */}
                {isRunning && (
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 font-mono text-sm overflow-y-auto h-40">
                    {agentLogs.map((line, i) => (
                      <p key={i} className="animate-pulse">
                        {line}
                      </p>
                    ))}
                  </div>
                )}

                {/* Output Section */}
                {result && !isRunning && (
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm">
                    {result.ok ? (
                      <div>
                        <h4 className="font-semibold text-gray-800 flex items-center mb-2">
                          <FileText className="w-4 h-4 mr-2" /> Output Data
                        </h4>
                        <pre className="text-xs bg-gray-100 rounded-lg p-2 overflow-x-auto max-h-40">
                          {JSON.stringify(result.data, null, 2)}
                        </pre>
                      </div>
                    ) : (
                      <p className="text-red-600 font-medium">{result.error}</p>
                    )}
                  </div>
                )}

                <button
                  onClick={() =>
                    setExpandedAgent(expandedAgent === agent ? null : agent)
                  }
                  className="text-indigo-600 text-sm flex items-center gap-1 mt-2"
                >
                  {expandedAgent === agent ? (
                    <>
                      Hide Console <ChevronUp className="w-4 h-4" />
                    </>
                  ) : (
                    <>
                      Show Console <ChevronDown className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
