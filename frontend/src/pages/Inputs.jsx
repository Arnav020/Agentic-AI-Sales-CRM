import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Upload,
  FileJson,
  FileText,
  CheckCircle,
  AlertCircle,
  Building2,
  Edit,
  XCircle,
  Save,
  Sparkles,
  Users,
  MapPin,
  Calendar,
  Mail,
  Phone,
  User,
  Briefcase,
  Globe,
  FileCode,
  Tag,
  TrendingUp,
  HelpCircle,
  X,
} from "lucide-react";

export default function Inputs() {
  const [csvFile, setCsvFile] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [message, setMessage] = useState("");
  const [inputStatus, setInputStatus] = useState({
    companies: false,
    customer_requirements: false,
  });
  const [editMode, setEditMode] = useState({
    companies: false,
    customer_requirements: false,
  });
  const [showTemplateExample, setShowTemplateExample] = useState(false);

  const username = localStorage.getItem("username");
  const BASE_URL = "http://127.0.0.1:8000";

  const [formData, setFormData] = useState({
    industry: "",
    preferred_keywords: "",
    headquarters: "",
    founded_after: "",
    employee_range: "",
    sender_name: "",
    sender_email: "",
    sender_designation: "",
    sender_phone: "",
    company_name: "",
    company_description: "",
    company_website: "",
  });

  // 🔍 Check existing input files
  useEffect(() => {
    if (!username) return;
    axios
      .get(`${BASE_URL}/users/${username}/has_inputs`)
      .then((res) => {
        const files = res.data.files || [];
        setInputStatus({
          companies: files.includes("companies.json"),
          customer_requirements: files.includes("customer_requirements.json"),
        });
      })
      .catch((err) => console.error("Error fetching input status:", err));
  }, [username]);

  // 🔹 Upload companies CSV
  const handleCsvUpload = async (e) => {
    e.preventDefault();
    if (!csvFile) return;
    const form = new FormData();
    form.append("file", csvFile);
    try {
      const res = await axios.post(`${BASE_URL}/data/${username}/upload_companies_csv`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMessage(res.data.message);
      setInputStatus((prev) => ({ ...prev, companies: true }));
      setEditMode((prev) => ({ ...prev, companies: false }));
    } catch (err) {
      setMessage("❌ CSV upload failed.");
    }
  };

  // 🔹 Save customer requirements
  const handleRequirementsSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        industry: formData.industry.split(",").map((s) => s.trim()),
        preferred_keywords: formData.preferred_keywords.split(",").map((s) => s.trim()),
        headquarters: formData.headquarters.split(",").map((s) => s.trim()),
        min_funding_signal: 0.3,
        max_negative_signal: 0.4,
        hiring_required: true,
        employee_search_top_percent: 0.2,
        founded_after: Number(formData.founded_after) || 2012,
        employee_range: formData.employee_range.split(",").map(Number),
        company_profile: {
          name: formData.company_name,
          description: formData.company_description,
          website: formData.company_website,
        },
        communication_settings: {
          sender_name: formData.sender_name,
          sender_designation: formData.sender_designation,
          sender_email: formData.sender_email,
          sender_phone: formData.sender_phone,
        },
      };

      const form = new FormData();
      form.append("requirements_json", JSON.stringify(payload));
      if (templateFile) form.append("template_file", templateFile);

      const res = await axios.post(`${BASE_URL}/data/${username}/save_customer_requirements`, form);
      setMessage(res.data.message);
      setInputStatus((prev) => ({ ...prev, customer_requirements: true }));
      setEditMode((prev) => ({ ...prev, customer_requirements: false }));
    } catch (err) {
      setMessage("❌ Could not save requirements.");
    }
  };

  // ✨ Industry and keyword suggestions
  const industrySuggestions = [
    "Food & Beverage Technology",
    "Restaurant Analytics",
    "Hospitality Tech",
    "Cloud Kitchens",
    "SaaS for Retail",
    "IoT for Food Industry",
    "Kitchen Automation",
  ];

  const keywordSuggestions = [
    "restaurant",
    "food",
    "beverage",
    "cloud kitchen",
    "menu analytics",
    "customer experience",
    "inventory management",
  ];

  const addSuggestion = (key, value) => {
    if (!formData[key].includes(value)) {
      setFormData({
        ...formData,
        [key]: formData[key] ? `${formData[key]}, ${value}` : value,
      });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-6 md:p-10">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold text-gray-900 mb-2">Input Configuration</h1>
              <p className="text-gray-600">Configure your data sources and customer requirements</p>
            </div>
            <div className="bg-indigo-50 p-4 rounded-xl">
              <Sparkles className="text-indigo-600 w-8 h-8" />
            </div>
          </div>
        </div>

        {/* Alert Message */}
        {message && (
          <div
            className={`p-4 rounded-xl flex items-center space-x-3 shadow-md transition-all ${
              message.startsWith("✅")
                ? "bg-green-50 border border-green-200"
                : "bg-red-50 border border-red-200"
            }`}
          >
            {message.startsWith("✅") ? (
              <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0" />
            )}
            <span className={`font-semibold ${
              message.startsWith("✅") ? "text-green-800" : "text-red-800"
            }`}>
              {message}
            </span>
          </div>
        )}

        {/* Progress Tracker */}
        <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
            Configuration Progress
          </h3>
          <div className="flex items-center space-x-4">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">Companies Data</span>
                <span className={`text-xs font-semibold ${
                  inputStatus.companies ? "text-green-600" : "text-gray-400"
                }`}>
                  {inputStatus.companies ? "Complete" : "Pending"}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${
                    inputStatus.companies ? "bg-green-500 w-full" : "bg-gray-300 w-0"
                  }`}
                ></div>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">Requirements</span>
                <span className={`text-xs font-semibold ${
                  inputStatus.customer_requirements ? "text-green-600" : "text-gray-400"
                }`}>
                  {inputStatus.customer_requirements ? "Complete" : "Pending"}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${
                    inputStatus.customer_requirements ? "bg-green-500 w-full" : "bg-gray-300 w-0"
                  }`}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Companies CSV Upload */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden">
          <div className="bg-gradient-to-r from-indigo-500 to-blue-500 p-6">
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-3">
                <div className="bg-white/20 backdrop-blur-sm p-3 rounded-xl">
                  <Upload className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white">Companies CSV Upload</h2>
                  <p className="text-indigo-100 text-sm">Upload your target companies list</p>
                </div>
              </div>
              {inputStatus.companies && !editMode.companies && (
                <div className="flex items-center bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full">
                  <CheckCircle className="w-5 h-5 mr-2 text-white" />
                  <span className="text-white font-semibold text-sm">Completed</span>
                </div>
              )}
            </div>
          </div>

          <div className="p-6">
            {inputStatus.companies && !editMode.companies ? (
              <div className="text-center py-8">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
                  <CheckCircle className="w-8 h-8 text-green-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">CSV File Uploaded</h3>
                <p className="text-gray-600 mb-6">Your companies data has been successfully uploaded</p>
                <button
                  onClick={() => setEditMode((p) => ({ ...p, companies: true }))}
                  className="inline-flex items-center px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-colors shadow-md"
                >
                  <Edit className="w-5 h-5 mr-2" />
                  Upload New File
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-indigo-400 transition-colors">
                  <FileJson className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setCsvFile(e.target.files[0])}
                    className="hidden"
                    id="csv-upload"
                  />
                  <label
                    htmlFor="csv-upload"
                    className="cursor-pointer inline-flex items-center px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-medium transition-colors"
                  >
                    <Upload className="w-5 h-5 mr-2" />
                    Choose CSV File
                  </label>
                  {csvFile && (
                    <p className="mt-3 text-sm text-gray-600">
                      Selected: <span className="font-semibold">{csvFile.name}</span>
                    </p>
                  )}
                </div>

                <div className="flex justify-end gap-3">
                  <button
                    onClick={handleCsvUpload}
                    disabled={!csvFile}
                    className="inline-flex items-center px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg font-semibold transition-colors shadow-md"
                  >
                    <Save className="w-5 h-5 mr-2" />
                    {editMode.companies ? "Save Changes" : "Upload"}
                  </button>
                  {editMode.companies && (
                    <button
                      onClick={() => setEditMode((p) => ({ ...p, companies: false }))}
                      className="inline-flex items-center px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold transition-colors"
                    >
                      <XCircle className="w-5 h-5 mr-2" />
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Customer Requirements */}
        <form
          onSubmit={handleRequirementsSubmit}
          className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden"
        >
          <div className="bg-gradient-to-r from-blue-500 to-indigo-500 p-6">
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-3">
                <div className="bg-white/20 backdrop-blur-sm p-3 rounded-xl">
                  <FileText className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white">Customer Requirements</h2>
                  <p className="text-blue-100 text-sm">Define your target criteria and preferences</p>
                </div>
              </div>
              {inputStatus.customer_requirements && !editMode.customer_requirements && (
                <div className="flex items-center bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full">
                  <CheckCircle className="w-5 h-5 mr-2 text-white" />
                  <span className="text-white font-semibold text-sm">Completed</span>
                </div>
              )}
            </div>
          </div>

          <div className="p-6">
            {inputStatus.customer_requirements && !editMode.customer_requirements ? (
              <div className="text-center py-8">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
                  <CheckCircle className="w-8 h-8 text-green-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Requirements Configured</h3>
                <p className="text-gray-600 mb-6">Your customer requirements have been saved</p>
                <button
                  onClick={() => setEditMode((p) => ({ ...p, customer_requirements: true }))}
                  type="button"
                  className="inline-flex items-center px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-colors shadow-md"
                >
                  <Edit className="w-5 h-5 mr-2" />
                  Edit Configuration
                </button>
              </div>
            ) : (
              <div className="space-y-8">
                {/* Company Profile Section */}
                <div className="bg-gradient-to-br from-indigo-50 to-blue-50 p-6 rounded-xl border border-indigo-100">
                  <div className="flex items-center space-x-2 mb-6">
                    <Building2 className="w-6 h-6 text-indigo-600" />
                    <h3 className="text-lg font-bold text-gray-900">Company Profile</h3>
                  </div>
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Briefcase className="w-4 h-4 mr-2 text-indigo-600" />
                        Company Name
                      </label>
                      <input
                        type="text"
                        value={formData.company_name}
                        onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                        placeholder="Enter your company name"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <FileText className="w-4 h-4 mr-2 text-indigo-600" />
                        Company Description
                      </label>
                      <textarea
                        value={formData.company_description}
                        onChange={(e) => setFormData({ ...formData, company_description: e.target.value })}
                        placeholder="Describe what your company does..."
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
                        rows={3}
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Globe className="w-4 h-4 mr-2 text-indigo-600" />
                        Company Website
                      </label>
                      <input
                        type="text"
                        value={formData.company_website}
                        onChange={(e) => setFormData({ ...formData, company_website: e.target.value })}
                        placeholder="https://yourcompany.com"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                  </div>
                </div>

                {/* Target Criteria */}
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border border-blue-100">
                  <div className="flex items-center space-x-2 mb-6">
                    <TrendingUp className="w-6 h-6 text-blue-600" />
                    <h3 className="text-lg font-bold text-gray-900">Target Criteria</h3>
                  </div>
                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Industries with Suggestions */}
                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Tag className="w-4 h-4 mr-2 text-blue-600" />
                        Industries (comma separated)
                      </label>
                      <input
                        type="text"
                        value={formData.industry}
                        onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                        placeholder="e.g., Food Tech, Restaurant Analytics"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all mb-3"
                      />
                      <div className="flex flex-wrap gap-2">
                        {industrySuggestions.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => addSuggestion("industry", s)}
                            className="px-3 py-1.5 bg-white border border-blue-200 text-blue-700 rounded-full hover:bg-blue-50 transition-colors text-xs font-medium"
                          >
                            + {s}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Keywords with Suggestions */}
                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Sparkles className="w-4 h-4 mr-2 text-blue-600" />
                        Preferred Keywords
                      </label>
                      <input
                        type="text"
                        value={formData.preferred_keywords}
                        onChange={(e) => setFormData({ ...formData, preferred_keywords: e.target.value })}
                        placeholder="e.g., restaurant, food, beverage"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all mb-3"
                      />
                      <div className="flex flex-wrap gap-2">
                        {keywordSuggestions.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => addSuggestion("preferred_keywords", s)}
                            className="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 rounded-full hover:bg-indigo-50 transition-colors text-xs font-medium"
                          >
                            + {s}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <MapPin className="w-4 h-4 mr-2 text-blue-600" />
                        Headquarters
                      </label>
                      <input
                        type="text"
                        value={formData.headquarters}
                        onChange={(e) => setFormData({ ...formData, headquarters: e.target.value })}
                        placeholder="e.g., San Francisco, New York"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>

                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Calendar className="w-4 h-4 mr-2 text-blue-600" />
                        Founded After (year)
                      </label>
                      <input
                        type="text"
                        value={formData.founded_after}
                        onChange={(e) => setFormData({ ...formData, founded_after: e.target.value })}
                        placeholder="e.g., 2015"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>

                    <div className="md:col-span-2">
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Users className="w-4 h-4 mr-2 text-blue-600" />
                        Employee Range (min, max)
                      </label>
                      <input
                        type="text"
                        value={formData.employee_range}
                        onChange={(e) => setFormData({ ...formData, employee_range: e.target.value })}
                        placeholder="e.g., 10, 500"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                  </div>
                </div>

                {/* Communication Settings */}
                <div className="bg-gradient-to-br from-slate-50 to-gray-50 p-6 rounded-xl border border-gray-200">
                  <div className="flex items-center space-x-2 mb-6">
                    <Mail className="w-6 h-6 text-gray-600" />
                    <h3 className="text-lg font-bold text-gray-900">Communication Settings</h3>
                  </div>
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <User className="w-4 h-4 mr-2 text-gray-600" />
                        Sender Name
                      </label>
                      <input
                        type="text"
                        value={formData.sender_name}
                        onChange={(e) => setFormData({ ...formData, sender_name: e.target.value })}
                        placeholder="John Doe"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Briefcase className="w-4 h-4 mr-2 text-gray-600" />
                        Sender Designation
                      </label>
                      <input
                        type="text"
                        value={formData.sender_designation}
                        onChange={(e) => setFormData({ ...formData, sender_designation: e.target.value })}
                        placeholder="Sales Manager"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Mail className="w-4 h-4 mr-2 text-gray-600" />
                        Sender Email
                      </label>
                      <input
                        type="email"
                        value={formData.sender_email}
                        onChange={(e) => setFormData({ ...formData, sender_email: e.target.value })}
                        placeholder="john@company.com"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="flex items-center text-sm font-semibold text-gray-700 mb-2">
                        <Phone className="w-4 h-4 mr-2 text-gray-600" />
                        Sender Phone
                      </label>
                      <input
                        type="text"
                        value={formData.sender_phone}
                        onChange={(e) => setFormData({ ...formData, sender_phone: e.target.value })}
                        placeholder="+1 (555) 123-4567"
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 focus:border-transparent outline-none transition-all"
                      />
                    </div>
                  </div>
                </div>

                {/* Template Upload */}
                <div className="bg-gradient-to-br from-amber-50 to-orange-50 p-6 rounded-xl border border-amber-200">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-2">
                      <FileCode className="w-6 h-6 text-amber-600" />
                      <h3 className="text-lg font-bold text-gray-900">HTML Template (Optional)</h3>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowTemplateExample(!showTemplateExample)}
                      className="flex items-center space-x-1 text-amber-600 hover:text-amber-700 transition-colors"
                      title="View sample template"
                    >
                      <HelpCircle className="w-5 h-5" />
                      <span className="text-sm font-medium">Sample Format</span>
                    </button>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">Upload a custom HTML email template for your campaigns</p>
                  <input
                    type="file"
                    accept=".html"
                    onChange={(e) => setTemplateFile(e.target.files[0])}
                    className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-amber-100 file:text-amber-700 hover:file:bg-amber-200 cursor-pointer"
                  />
                  {templateFile && (
                    <p className="mt-2 text-sm text-gray-600">
                      Selected: <span className="font-semibold">{templateFile.name}</span>
                    </p>
                  )}

                  {/* Sample Template Modal */}
                  {showTemplateExample && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                      <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden">
                        <div className="bg-gradient-to-r from-amber-500 to-orange-500 p-6 flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div className="bg-white/20 backdrop-blur-sm p-2 rounded-lg">
                              <FileCode className="w-6 h-6 text-white" />
                            </div>
                            <div>
                              <h3 className="text-xl font-bold text-white">Sample HTML Template</h3>
                              <p className="text-amber-100 text-sm">Copy and customize this template</p>
                            </div>
                          </div>
                          <button
                            onClick={() => setShowTemplateExample(false)}
                            className="text-white hover:bg-white/20 p-2 rounded-lg transition-colors"
                          >
                            <X className="w-6 h-6" />
                          </button>
                        </div>
                        <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
                          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                            <pre className="text-xs text-gray-800 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
{`<!-- SUBJECT: Boost restaurant efficiency 🍳 with AI-powered kitchen insights -->
<div dir="ltr" style="font-family:Arial,sans-serif;font-size:11pt;width:100%; line-height:1.5;">
  <p><strong>Hi {{name}},</strong></p>

  <p>Hope you're having a great day 😊</p>

  <p>
    I'm reaching out from <strong>{{company}}</strong>, where we help <strong>restaurants</strong> and 
    <strong>cloud kitchens</strong> transform operations with <strong>AI-powered analytics</strong> 
    and <strong>smart kitchen automation</strong>.
  </p>

  <p>
    Our platform tracks <strong>order flow</strong>, <strong>wastage</strong>, and <strong>inventory efficiency</strong> in real time — 
    helping food brands reduce waste 🍲, improve turnaround ⏱️, and enhance customer experience 💡.
  </p>

  <p>
    Would you be open to a short 10–15 minute chat next week to see how {{company}} could help optimize 
    your operations or expansion plans?
  </p>

  <p>Looking forward to connecting! 🙌</p>
</div>`}
                            </pre>
                          </div>
                          <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
                            <h4 className="font-semibold text-blue-900 mb-2 flex items-center">
                              <Sparkles className="w-4 h-4 mr-2" />
                              Available Variables
                            </h4>
                            <ul className="text-sm text-blue-800 space-y-1">
                              <li><code className="bg-blue-100 px-2 py-0.5 rounded">{'{{name}}'}</code> - Recipient's name</li>
                              <li><code className="bg-blue-100 px-2 py-0.5 rounded">{'{{company}}'}</code> - Your company name</li>
                              <li><code className="bg-blue-100 px-2 py-0.5 rounded">{'{{email}}'}</code> - Recipient's email</li>
                              <li><code className="bg-blue-100 px-2 py-0.5 rounded">{'{{website}}'}</code> - Recipient's website</li>
                            </ul>
                          </div>
                          <div className="mt-4 flex justify-end">
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(`<!-- SUBJECT: Boost restaurant efficiency 🍳 with AI-powered kitchen insights -->
<div dir="ltr" style="font-family:Arial,sans-serif;font-size:11pt;width:100%; line-height:1.5;">
  <p><strong>Hi {{name}},</strong></p>

  <p>Hope you're having a great day 😊</p>

  <p>
    I'm reaching out from <strong>{{company}}</strong>, where we help <strong>restaurants</strong> and 
    <strong>cloud kitchens</strong> transform operations with <strong>AI-powered analytics</strong> 
    and <strong>smart kitchen automation</strong>.
  </p>

  <p>
    Our platform tracks <strong>order flow</strong>, <strong>wastage</strong>, and <strong>inventory efficiency</strong> in real time — 
    helping food brands reduce waste 🍲, improve turnaround ⏱️, and enhance customer experience 💡.
  </p>

  <p>
    Would you be open to a short 10–15 minute chat next week to see how {{company}} could help optimize 
    your operations or expansion plans?
  </p>

  <p>Looking forward to connecting! 🙌</p>
</div>`);
                                alert('Template copied to clipboard!');
                              }}
                              className="px-6 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-semibold transition-colors"
                            >
                              Copy Template
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
                  <button
                    type="submit"
                    className="inline-flex items-center px-8 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-colors shadow-md"
                  >
                    <Save className="w-5 h-5 mr-2" />
                    Save Configuration
                  </button>
                  {inputStatus.customer_requirements && (
                    <button
                      type="button"
                      onClick={() => setEditMode((p) => ({ ...p, customer_requirements: false }))}
                      className="inline-flex items-center px-8 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold transition-colors"
                    >
                      <XCircle className="w-5 h-5 mr-2" />
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}