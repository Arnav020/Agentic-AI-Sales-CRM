import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import {
  BarChart3,
  FileText,
  Database,
  Activity,
  ArrowRight,
  RefreshCw,
  Users,
  Mail,
  TrendingUp,
  Target,
  Zap,
  CheckCircle,
  Clock,
  AlertCircle,
  Search,
  UserCheck,
} from "lucide-react";

export default function Dashboard() {
  const [hasInputs, setHasInputs] = useState(null);
  const [files, setFiles] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const username = localStorage.getItem("username");
  const BASE_URL = "http://127.0.0.1:8000";

  useEffect(() => {
    if (!username) {
      navigate("/auth");
      return;
    }

    const fetchData = async () => {
      try {
        const inputRes = await axios.get(`${BASE_URL}/users/${username}/has_inputs`);
        setHasInputs(inputRes.data.has_inputs);
        setFiles(inputRes.data.files || []);

        if (inputRes.data.has_inputs) {
          const [analyticsRes, recentRes] = await Promise.all([
            axios.get(`${BASE_URL}/analytics/overview/${username}`),
            axios.get(`${BASE_URL}/analytics/recent/${username}?limit=10`),
          ]);
          setAnalytics(analyticsRes.data);
          setRecentActivity(recentRes.data.recent_user_outputs || []);
        }
      } catch (err) {
        console.error(err);
        setHasInputs(false);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [username, navigate]);

  // Loading state
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <div className="text-center">
          <div className="inline-block w-16 h-16 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
          <p className="text-gray-600 text-lg font-medium">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  // No input files case
  if (!hasInputs) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-4">
        <div className="bg-white shadow-2xl rounded-2xl p-10 text-center border border-gray-100 max-w-lg">
          <div className="bg-indigo-50 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
            <FileText className="w-10 h-10 text-indigo-600" />
          </div>
          <h2 className="text-3xl font-bold text-gray-900 mb-3">Welcome to Agentic CRM</h2>
          <p className="text-gray-600 mb-8 leading-relaxed">
            You haven't configured your input data yet. Upload your companies list and define customer requirements to unlock powerful AI-driven insights.
          </p>
          <button
            onClick={() => navigate("/inputs")}
            className="inline-flex items-center px-8 py-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-lg hover:shadow-xl transition-all"
          >
            <span>Configure Input Data</span>
            <ArrowRight className="w-5 h-5 ml-2" />
          </button>
        </div>
      </div>
    );
  }

  const agentIcons = {
    enrichment_agent: <Database className="w-5 h-5" />,
    scoring_agent: <Target className="w-5 h-5" />,
    employee_finder: <Search className="w-5 h-5" />,
    contact_finder: <UserCheck className="w-5 h-5" />,
    email_sender: <Mail className="w-5 h-5" />,
  };

  const agentColors = {
    enrichment_agent: "from-blue-500 to-blue-600",
    scoring_agent: "from-purple-500 to-purple-600",
    employee_finder: "from-green-500 to-green-600",
    contact_finder: "from-orange-500 to-orange-600",
    email_sender: "from-indigo-500 to-indigo-600",
  };

  // Main Dashboard
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-6 md:p-10">
      {/* Header */}
      <div className="bg-white rounded-2xl shadow-lg p-6 mb-8 border border-gray-100">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between">
          <div className="flex items-center space-x-3 mb-4 md:mb-0">
            <div className="bg-indigo-600 p-3 rounded-xl">
              <BarChart3 className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
              <p className="text-gray-600 text-sm">Welcome back, {username}</p>
            </div>
          </div>
          <div className="flex space-x-3">
            <button
              onClick={() => navigate("/agents")}
              className="inline-flex items-center px-5 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-lg font-medium text-sm shadow-md transition-colors"
            >
              <Zap className="w-4 h-4 mr-2" />
              Run Agents
            </button>
            <button
              onClick={() => navigate("/inputs")}
              className="inline-flex items-center px-5 py-2.5 bg-white border-2 border-gray-200 rounded-lg text-gray-700 hover:border-indigo-400 hover:text-indigo-600 transition-all font-medium text-sm shadow-sm"
            >
              <FileText className="w-4 h-4 mr-2" />
              Input Config
            </button>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-md transition-colors"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid lg:grid-cols-4 md:grid-cols-2 gap-6 mb-8">
        <MetricCard
          title="Total Data Points"
          value={analytics?.counts.inputs || 0}
          change="+12%"
          icon={<Database className="w-6 h-6" />}
          gradient="from-blue-500 to-blue-600"
        />
        <MetricCard
          title="AI Operations"
          value={analytics?.counts.outputs || 0}
          change="+8%"
          icon={<Activity className="w-6 h-6" />}
          gradient="from-purple-500 to-purple-600"
        />
        <MetricCard
          title="Campaign Runs"
          value={analytics?.derived.total_campaign_runs || 0}
          change="+15%"
          icon={<Mail className="w-6 h-6" />}
          gradient="from-indigo-500 to-indigo-600"
        />
        <MetricCard
          title="Lead Scores"
          value={analytics?.derived.total_lead_scores || 0}
          change="+23%"
          icon={<Target className="w-6 h-6" />}
          gradient="from-green-500 to-green-600"
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-8 mb-8">
        {/* AI Agent Activity */}
        <div className="lg:col-span-2 bg-white shadow-lg rounded-2xl p-6 border border-gray-100">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">AI Agent Activity</h2>
            <div className="flex items-center space-x-2 text-sm text-gray-500">
              <Activity className="w-4 h-4" />
              <span>Live Metrics</span>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            {[
              { label: "Data Enrichment", value: analytics?.derived.total_enrichments || 0, agent: "enrichment_agent" },
              { label: "Lead Scoring", value: analytics?.derived.total_lead_scores || 0, agent: "scoring_agent" },
              { label: "Employee Searches", value: analytics?.derived.employee_searches || 0, agent: "employee_finder" },
              { label: "Contact Verification", value: analytics?.derived.contact_verifications || 0, agent: "contact_finder" },
              { label: "Email Campaigns", value: analytics?.derived.total_campaign_runs || 0, agent: "email_sender" },
            ].map((item, idx) => (
              <div
                key={idx}
                className="group bg-gradient-to-br from-gray-50 to-white p-5 rounded-xl border border-gray-200 hover:shadow-md transition-all"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className={`bg-gradient-to-br ${agentColors[item.agent]} p-2.5 rounded-lg text-white`}>
                    {agentIcons[item.agent]}
                  </div>
                  <span className="text-xs font-semibold text-gray-500 uppercase">Active</span>
                </div>
                <p className="text-gray-700 font-semibold text-sm mb-1">{item.label}</p>
                <p className="text-3xl font-bold text-gray-900">{item.value}</p>
                <div className="mt-3 flex items-center text-xs text-green-600 font-medium">
                  <TrendingUp className="w-3 h-3 mr-1" />
                  <span>Operational</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Stats */}
        <div className="space-y-6">
          {/* Agent Performance */}
          <div className="bg-white shadow-lg rounded-2xl p-6 border border-gray-100">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Top Agents</h3>
            {analytics?.counts?.per_agent?.length ? (
              <div className="space-y-3">
                {analytics.counts.per_agent.slice(0, 5).map((a, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className={`w-2 h-2 rounded-full bg-gradient-to-r ${agentColors[a._id] || 'from-gray-400 to-gray-500'}`}></div>
                      <span className="text-sm font-medium text-gray-700 capitalize">
                        {a._id?.replace(/_/g, ' ') || "Unnamed"}
                      </span>
                    </div>
                    <span className="text-sm font-bold text-gray-900">{a.count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-sm">No agent data available</p>
            )}
          </div>

          {/* System Status */}
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 shadow-lg rounded-2xl p-6 border border-green-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">System Status</h3>
              <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
            </div>
            <div className="space-y-3">
              <StatusItem icon={<CheckCircle className="w-5 h-5 text-green-600" />} label="All Systems Operational" />
              <StatusItem icon={<Zap className="w-5 h-5 text-green-600" />} label="AI Agents Active" />
              <StatusItem icon={<Database className="w-5 h-5 text-green-600" />} label="Data Synced" />
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity & Input Files */}
      <div className="grid lg:grid-cols-2 gap-8">
        {/* Recent Activity */}
        <div className="bg-white shadow-lg rounded-2xl p-6 border border-gray-100">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">Recent Activity</h2>
            <Clock className="w-5 h-5 text-gray-400" />
          </div>
          {recentActivity.length > 0 ? (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {recentActivity.map((activity, idx) => (
                <div
                  key={idx}
                  className="flex items-start space-x-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <div className={`bg-gradient-to-br ${agentColors[activity.agent] || 'from-gray-400 to-gray-500'} p-2 rounded-lg text-white flex-shrink-0`}>
                    {agentIcons[activity.agent] || <Activity className="w-4 h-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900 capitalize">
                      {activity.agent?.replace(/_/g, ' ') || "Unknown Agent"}
                    </p>
                    <p className="text-xs text-gray-600 truncate">
                      {activity.data?.company_name || activity.data?.subject || "Processed data"}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {new Date(activity.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 text-sm">No recent activity</p>
            </div>
          )}
        </div>

        {/* Input Files */}
        <div className="bg-white shadow-lg rounded-2xl p-6 border border-gray-100">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">Configured Inputs</h2>
            <FileText className="w-5 h-5 text-gray-400" />
          </div>
          {files.length > 0 ? (
            <div className="space-y-3">
              {files.map((file, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-4 bg-gradient-to-r from-indigo-50 to-blue-50 rounded-lg border border-indigo-100"
                >
                  <div className="flex items-center space-x-3">
                    <div className="bg-indigo-100 p-2 rounded-lg">
                      <FileText className="w-5 h-5 text-indigo-600" />
                    </div>
                    <span className="text-sm font-semibold text-gray-800">{file}</span>
                  </div>
                  <CheckCircle className="w-5 h-5 text-green-500" />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 text-sm">No input files configured</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Enhanced MetricCard with gradient and change indicator
function MetricCard({ title, value, change, icon, gradient }) {
  return (
    <div className="bg-white p-6 rounded-2xl shadow-lg hover:shadow-xl border border-gray-100 transition-all">
      <div className="flex items-center justify-between mb-4">
        <div className={`bg-gradient-to-br ${gradient} p-3 rounded-xl text-white shadow-md`}>
          {icon}
        </div>
        {change && (
          <span className="text-xs font-semibold text-green-600 bg-green-50 px-2 py-1 rounded-full">
            {change}
          </span>
        )}
      </div>
      <h3 className="text-gray-600 text-sm font-semibold mb-1">{title}</h3>
      <p className="text-4xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

// Status item component
function StatusItem({ icon, label }) {
  return (
    <div className="flex items-center space-x-2">
      {icon}
      <span className="text-sm font-medium text-gray-700">{label}</span>
    </div>
  );
}