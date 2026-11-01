#include "SettingsDialog.h"

namespace OmniStream {

SettingsDialog::SettingsDialog(QWidget* parent) : QDialog(parent) {
    setWindowTitle("OmniStream Pro - Preferences & Settings");
    setFixedSize(520, 380);
    setWindowFlags(windowFlags() & ~Qt::WindowContextHelpButtonHint);
    setupUI();
}

void SettingsDialog::setupUI() {
    auto* rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(24, 20, 24, 20);
    rootLayout->setSpacing(16);

    auto& sm = SettingsManager::GetInstance();
    const auto& current = sm.GetSettings();

    // Dialog Header
    auto* lblHeader = new QLabel("Preferences & Engine Configuration", this);
    lblHeader->setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;");
    rootLayout->addWidget(lblHeader);

    auto* grid = new QGridLayout();
    grid->setHorizontalSpacing(16);
    grid->setVerticalSpacing(14);

    // 1. Max Concurrent Downloads
    auto* lblConcur = new QLabel("Max Concurrent Downloads:", this);
    lblConcur->setStyleSheet("color: #94a3b8; font-weight: 600;");
    m_spinConcurrency = new QSpinBox(this);
    m_spinConcurrency->setRange(1, 10);
    m_spinConcurrency->setValue(current.max_concurrent);
    m_spinConcurrency->setStyleSheet("background-color: #090d13; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 4px;");
    grid->addWidget(lblConcur, 0, 0);
    grid->addWidget(m_spinConcurrency, 0, 1);

    // 2. Default Save Directory
    auto* lblDir = new QLabel("Default Save Folder:", this);
    lblDir->setStyleSheet("color: #94a3b8; font-weight: 600;");
    auto* dirBox = new QWidget(this);
    auto* dirLayout = new QHBoxLayout(dirBox);
    dirLayout->setContentsMargins(0, 0, 0, 0);
    dirLayout->setSpacing(6);

    m_editDefaultDir = new QLineEdit(QString::fromStdString(current.default_save_dir), this);
    m_editDefaultDir->setStyleSheet("background-color: #090d13; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px;");
    m_btnBrowse = new QPushButton("Browse...", this);
    m_btnBrowse->setStyleSheet("background-color: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 4px 10px; font-weight: 600;");
    connect(m_btnBrowse, &QPushButton::clicked, this, &SettingsDialog::onBrowseFolder);

    dirLayout->addWidget(m_editDefaultDir);
    dirLayout->addWidget(m_btnBrowse);
    grid->addWidget(lblDir, 1, 0);
    grid->addWidget(dirBox, 1, 1);

    // 3. Speed Limit
    auto* lblSpeed = new QLabel("Global Speed Limit:", this);
    lblSpeed->setStyleSheet("color: #94a3b8; font-weight: 600;");
    m_comboSpeedLimit = new QComboBox(this);
    m_comboSpeedLimit->addItems({"Unlimited (Maximum Speed)", "5 MB/s", "10 MB/s", "20 MB/s", "50 MB/s"});
    m_comboSpeedLimit->setStyleSheet("background-color: #090d13; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 4px;");

    if (current.speed_limit == "5M") m_comboSpeedLimit->setCurrentIndex(1);
    else if (current.speed_limit == "10M") m_comboSpeedLimit->setCurrentIndex(2);
    else if (current.speed_limit == "20M") m_comboSpeedLimit->setCurrentIndex(3);
    else if (current.speed_limit == "50M") m_comboSpeedLimit->setCurrentIndex(4);
    else m_comboSpeedLimit->setCurrentIndex(0);

    grid->addWidget(lblSpeed, 2, 0);
    grid->addWidget(m_comboSpeedLimit, 2, 1);

    // 4. Duplicate Detection Checkbox
    m_checkDeduplication = new QCheckBox("Enable Real-time Duplicate Prevention (Unique IDs & URLs)", this);
    m_checkDeduplication->setChecked(current.duplicate_detection);
    m_checkDeduplication->setStyleSheet("color: #f0f6fc; font-size: 12px;");
    grid->addWidget(m_checkDeduplication, 3, 0, 1, 2);

    // 5. Auto Start Downloads Checkbox
    m_checkAutoStart = new QCheckBox("Automatically start downloads when captured from Chrome Extension", this);
    m_checkAutoStart->setChecked(current.auto_start_downloads);
    m_checkAutoStart->setStyleSheet("color: #f0f6fc; font-size: 12px;");
    grid->addWidget(m_checkAutoStart, 4, 0, 1, 2);

    rootLayout->addLayout(grid);
    rootLayout->addStretch();

    // Dialog Action Buttons
    auto* btnLayout = new QHBoxLayout();
    btnLayout->addStretch();

    m_btnCancel = new QPushButton("Cancel", this);
    m_btnCancel->setStyleSheet("background-color: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 6px 16px; font-weight: 600;");
    connect(m_btnCancel, &QPushButton::clicked, this, &QDialog::reject);
    btnLayout->addWidget(m_btnCancel);

    m_btnSave = new QPushButton("Save Settings", this);
    m_btnSave->setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb); color: #ffffff; border: 1px solid #38bdf8; border-radius: 6px; padding: 6px 20px; font-weight: bold;");
    connect(m_btnSave, &QPushButton::clicked, this, &SettingsDialog::onSave);
    btnLayout->addWidget(m_btnSave);

    rootLayout->addLayout(btnLayout);

    setStyleSheet("QDialog { background-color: #161b22; color: #f0f6fc; font-family: 'Segoe UI', sans-serif; }");
}

void SettingsDialog::onBrowseFolder() {
    QString dir = QFileDialog::getExistingDirectory(
        this, "Select Default Download Folder", m_editDefaultDir->text()
    );
    if (!dir.isEmpty()) {
        m_editDefaultDir->setText(dir);
    }
}

void SettingsDialog::onSave() {
    auto& sm = SettingsManager::GetInstance();

    sm.SetMaxConcurrent(m_spinConcurrency->value());
    sm.SetSaveDir(m_editDefaultDir->text().toStdString());

    std::string speedStr = "unlimited";
    int speedIdx = m_comboSpeedLimit->currentIndex();
    if (speedIdx == 1) speedStr = "5M";
    else if (speedIdx == 2) speedStr = "10M";
    else if (speedIdx == 3) speedStr = "20M";
    else if (speedIdx == 4) speedStr = "50M";

    sm.SetSpeedLimit(speedStr);
    sm.SetDuplicateDetection(m_checkDeduplication->isChecked());
    sm.GetSettings().auto_start_downloads = m_checkAutoStart->isChecked();

    sm.Save();
    accept();
}

} // namespace OmniStream
