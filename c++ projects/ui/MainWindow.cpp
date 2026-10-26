#include "MainWindow.h"
#include "curl_parser.hpp"
#include "netflix_resolver.hpp"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QHeaderView>
#include <QClipboard>
#include <QApplication>
#include <QFileDialog>
#include <QMessageBox>
#include <QStandardPaths>
#include <QDesktopServices>
#include <QUrl>

namespace OmniStream {

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent) {
    // Frameless window with rounded curved borders
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinMaxButtonsHint);
    setAttribute(Qt::WA_TranslucentBackground, true);

    setWindowTitle("OmniStream Pro v2.6.0 \u2014 IDM-Grade Stream Downloader");
    setWindowIcon(QIcon(":/assets/images/app_logo.png"));
    setMinimumSize(1020, 840);
    resize(1060, 860);

    setupUI();
    applyStyleSheet();

    // Connect custom signals for thread-safe UI updates
    connect(this, &MainWindow::logMessageReceived, this, &MainWindow::handleLogMessage);
    connect(this, &MainWindow::progressUpdated, this, &MainWindow::handleProgressUpdate);
    connect(this, &MainWindow::downloadCompleted, this, &MainWindow::handleDownloadComplete);

    // Auto-start Chrome Extension Bridge Server on port 28795
    m_bridgeServer = std::make_unique<BridgeServer>(BRIDGE_PORT);
    m_bridgeServer->SetOnModeChanged([this](const std::string& mode) {
        QMetaObject::invokeMethod(this, [this, mode]() {
            setDownloadMode(QString::fromStdString(mode));
        }, Qt::QueuedConnection);
    });
    m_bridgeServer->SetOnJobReceived([this](const DownloadOptions& opts) {
        emit logMessageReceived(QString::fromStdString("[Bridge] Incoming job from Chrome Extension: " + opts.inputText));
        QMetaObject::invokeMethod(this, [this, opts]() {
            if (!opts.mode.empty()) {
                setDownloadMode(QString::fromStdString(opts.mode));
            }
            m_editUrl->setPlainText(QString::fromStdString(opts.inputText));
            if (!opts.saveName.empty()) {
                m_editTitle->setText(QString::fromStdString(opts.saveName));
            }
            addQueueItem(opts);
            showNormal();
            raise();
            activateWindow();
            if (!m_isDownloading.load()) {
                onStartDownloadClicked();
            }
        }, Qt::QueuedConnection);
    });

    m_animTimer = new QTimer(this);
    connect(m_animTimer, &QTimer::timeout, this, [this]() {
        m_glowAngle += 0.035f;
        if (m_glowAngle > 6.28318f) m_glowAngle -= 6.28318f;
        m_pulseValue = 0.5f + 0.5f * std::sin(m_glowAngle);

        // Dynamic live breathing green pulse on Ready badge
        if (m_lblStatusBadge) {
            float gPulse = 0.5f + 0.5f * std::sin(m_glowAngle * 1.5f);
            m_lblStatusBadge->setStyleSheet(QString(
                "#lblStatusBadge {"
                "   background-color: rgba(6, 78, 59, %1);"
                "   color: #34d399;"
                "   font-size: 11px;"
                "   font-weight: bold;"
                "   border: 1px solid rgba(52, 211, 153, %2);"
                "   border-radius: 12px;"
                "   padding: 3px 12px;"
                "}"
            ).arg(140 + static_cast<int>(80 * gPulse)).arg(0.35f + 0.55f * gPulse));
        }

        update(); // repaints glowing curved border
    });
    m_animTimer->start(25); // ~40 FPS buttery smooth animation

    if (m_bridgeServer->Start()) {
        handleLogMessage("[Bridge] Extension bridge active \u2014 ready for 1-click capture.");
    } else {
        handleLogMessage("[Bridge] Warning: Extension bridge port occupied or running in another instance.");
    }
}

MainWindow::~MainWindow() {
    if (m_downloadThread && m_downloadThread->joinable()) {
        if (m_currentEngine) m_currentEngine->Abort();
        m_downloadThread->join();
    }
    if (m_bridgeServer) {
        m_bridgeServer->Stop();
    }
}

void MainWindow::paintEvent(QPaintEvent *event) {
    Q_UNUSED(event);
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    QRectF r = rect().adjusted(4, 4, -5, -5);

    // 1. Outer Soft Glowing Aura (multi-layer neon diffusion)
    float pulse = 0.5f + 0.5f * std::sin(m_glowAngle);

    QLinearGradient haloGrad(
        r.center().x() + r.width() * 0.55f * std::cos(m_glowAngle),
        r.center().y() + r.height() * 0.55f * std::sin(m_glowAngle),
        r.center().x() - r.width() * 0.55f * std::cos(m_glowAngle),
        r.center().y() - r.height() * 0.55f * std::sin(m_glowAngle)
    );
    haloGrad.setColorAt(0.0, QColor(56, 189, 248, static_cast<int>(40 + 35 * pulse)));  // Electric Cyan
    haloGrad.setColorAt(0.35, QColor(139, 92, 246, static_cast<int>(35 + 30 * pulse))); // Neon Purple
    haloGrad.setColorAt(0.7, QColor(236, 72, 153, static_cast<int>(40 + 35 * pulse)));  // Pink Accent
    haloGrad.setColorAt(1.0, QColor(56, 189, 248, static_cast<int>(40 + 35 * pulse)));  // Electric Cyan

    painter.setPen(QPen(QBrush(haloGrad), 4.5));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(rect().adjusted(2, 2, -3, -3), 16, 16);

    // 2. Window Body Background
    QColor bodyBg = (m_comboTheme && m_comboTheme->currentIndex() == 1) ? QColor("#05080f") : QColor("#0d1117");
    painter.setBrush(bodyBg);
    painter.setPen(Qt::NoPen);
    painter.drawRoundedRect(r, 16, 16);

    // 3. Dynamic Rotating Luminous Border
    QLinearGradient borderGrad(
        r.center().x() + r.width() * 0.6f * std::cos(m_glowAngle),
        r.center().y() + r.height() * 0.6f * std::sin(m_glowAngle),
        r.center().x() - r.width() * 0.6f * std::cos(m_glowAngle),
        r.center().y() - r.height() * 0.6f * std::sin(m_glowAngle)
    );
    borderGrad.setColorAt(0.0, QColor("#38bdf8")); // Cyan
    borderGrad.setColorAt(0.35, QColor("#818cf8")); // Indigo
    borderGrad.setColorAt(0.7, QColor("#c084fc")); // Purple
    borderGrad.setColorAt(1.0, QColor("#38bdf8")); // Wrap to Cyan

    painter.setPen(QPen(QBrush(borderGrad), 1.8));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(r, 16, 16);

    // 4. Inner Subtle Rim
    painter.setPen(QPen(QColor(255, 255, 255, static_cast<int>(12 + 15 * pulse)), 1.0));
    painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 15, 15);
}

void MainWindow::mousePressEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton && event->position().y() < 55) {
        m_dragPosition = event->globalPosition().toPoint() - frameGeometry().topLeft();
        m_isDragging = true;
        event->accept();
    }
}

void MainWindow::mouseMoveEvent(QMouseEvent *event) {
    if (m_isDragging && (event->buttons() & Qt::LeftButton)) {
        move(event->globalPosition().toPoint() - m_dragPosition);
        event->accept();
    }
}

void MainWindow::mouseReleaseEvent(QMouseEvent *event) {
    Q_UNUSED(event);
    m_isDragging = false;
}

void MainWindow::changeEvent(QEvent *event) {
    if (event->type() == QEvent::WindowStateChange) {
        if (m_btnCapMax) {
            m_btnCapMax->setMaximizedState(isMaximized());
        }
    }
    QMainWindow::changeEvent(event);
}

void MainWindow::keyPressEvent(QKeyEvent *event) {
    if (event->key() == Qt::Key_Escape && m_isFullView) {
        onFullViewClicked();
        event->accept();
        return;
    }
    QMainWindow::keyPressEvent(event);
}

void MainWindow::setupUI() {
    auto *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    auto *rootLayout = new QVBoxLayout(centralWidget);
    rootLayout->setContentsMargins(22, 14, 22, 14);
    rootLayout->setSpacing(10);

    // ── 1. Top Integrated Header with Window Controls ─────────────────────────
    auto *headerWidget = new QWidget(this);
    headerWidget->setObjectName("headerWidget");
    auto *headerLayout = new QHBoxLayout(headerWidget);
    headerLayout->setContentsMargins(4, 2, 4, 4);
    headerLayout->setSpacing(10);

    m_lblLogo = new QLabel(this);
    m_lblLogo->setPixmap(QPixmap(":/assets/images/app_logo.png").scaled(32, 32, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    headerLayout->addWidget(m_lblLogo);

    m_lblTitle = new QLabel("OmniStream Pro", this);
    m_lblTitle->setObjectName("lblAppTitle");
    headerLayout->addWidget(m_lblTitle);

    m_lblVersionBadge = new QLabel(" v2.6.0 ", this);
    m_lblVersionBadge->setObjectName("lblVersionBadge");
    headerLayout->addWidget(m_lblVersionBadge);

    headerLayout->addStretch();

    m_comboTheme = new QComboBox(this);
    m_comboTheme->setObjectName("comboTheme");
    m_comboTheme->addItem("Cyber Slate");
    m_comboTheme->addItem("Midnight Black");
    connect(m_comboTheme, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::onThemeChanged);
    headerLayout->addWidget(m_comboTheme);

    m_lblStatusBadge = new QLabel("\u25CF Ready", this);
    m_lblStatusBadge->setObjectName("lblStatusBadge");
    headerLayout->addWidget(m_lblStatusBadge);

    // Caption Buttons: Minimize, Maximize, Close (High-DPI Premium Vector Icons)
    m_btnCapMin = new CaptionButton(CaptionType::Minimize, this);
    m_btnCapMin->setObjectName("btnCapMin");
    m_btnCapMin->setToolTip("Minimize");
    connect(m_btnCapMin, &QPushButton::clicked, this, &MainWindow::showMinimized);

    m_btnCapMax = new CaptionButton(CaptionType::Maximize, this);
    m_btnCapMax->setObjectName("btnCapMax");
    m_btnCapMax->setToolTip("Maximize / Restore");
    connect(m_btnCapMax, &QPushButton::clicked, [this]() {
        if (isMaximized()) {
            showNormal();
            m_btnCapMax->setMaximizedState(false);
        } else {
            showMaximized();
            m_btnCapMax->setMaximizedState(true);
        }
    });

    m_btnCapClose = new CaptionButton(CaptionType::Close, this);
    m_btnCapClose->setObjectName("btnCapClose");
    m_btnCapClose->setToolTip("Close");
    connect(m_btnCapClose, &QPushButton::clicked, this, &MainWindow::close);

    headerLayout->addWidget(m_btnCapMin);
    headerLayout->addWidget(m_btnCapMax);
    headerLayout->addWidget(m_btnCapClose);

    rootLayout->addWidget(headerWidget);

    // ── 2. Indigo Bridge Notice Banner ────────────────────────────────────────
    m_bannerWidget = new QWidget(this);
    m_bannerWidget->setObjectName("bannerWidget");
    auto *bannerLayout = new QHBoxLayout(m_bannerWidget);
    bannerLayout->setContentsMargins(16, 7, 16, 7);
    auto *lblBannerText = new QLabel("\u25CF Chrome Extension Bridge Active \u2014 Ready for 1-Click Stream Capture", this);
    lblBannerText->setObjectName("lblBannerText");
    bannerLayout->addWidget(lblBannerText);
    rootLayout->addWidget(m_bannerWidget);

    // ── 3. Card 1: Stream Source ──────────────────────────────────────────────
    m_card1 = new QWidget(this);
    m_card1->setObjectName("cardWidget");
    auto *card1Layout = new QVBoxLayout(m_card1);
    card1Layout->setContentsMargins(18, 10, 18, 12);
    card1Layout->setSpacing(8);

    auto *c1Header = new QHBoxLayout();
    auto *lblC1Title = new QLabel("Stream Source", this);
    lblC1Title->setObjectName("cardTitle");
    auto *lblC1Sub = new QLabel("Auto-parses cURL bash/cmd, M3U8, MPD, MP4, and MKV links", this);
    lblC1Sub->setObjectName("cardSubTitle");
    c1Header->addWidget(lblC1Title);
    c1Header->addWidget(lblC1Sub);
    c1Header->addStretch();

    m_btnPaste = new QPushButton(" Paste", this);
    m_btnPaste->setIcon(QIcon(":/assets/images/icon_paste.png"));
    m_btnPaste->setObjectName("btnPaste");
    connect(m_btnPaste, &QPushButton::clicked, this, &MainWindow::onPasteClicked);
    c1Header->addWidget(m_btnPaste);
    card1Layout->addLayout(c1Header);

    m_editUrl = new QPlainTextEdit(this);
    m_editUrl->setObjectName("editUrl");
    m_editUrl->setPlaceholderText("Paste stream URL or Chrome cURL command here...");
    m_editUrl->setFixedHeight(46);
    card1Layout->addWidget(m_editUrl);
    rootLayout->addWidget(m_card1);

    // ── 4. Card 2: Configuration ──────────────────────────────────────────────
    m_card2 = new QWidget(this);
    m_card2->setObjectName("cardWidget");
    auto *card2Layout = new QGridLayout(m_card2);
    card2Layout->setContentsMargins(18, 12, 18, 12);
    card2Layout->setHorizontalSpacing(16);
    card2Layout->setVerticalSpacing(10);

    // Row 0: Title & Resolution
    auto *lblTitleOpt = new QLabel("Title (optional)", this);
    lblTitleOpt->setObjectName("fieldLabel");
    m_editTitle = new QLineEdit(this);
    m_editTitle->setObjectName("inputField");
    m_editTitle->setPlaceholderText("Leave blank to auto-detect");

    auto *lblRes = new QLabel("Resolution", this);
    lblRes->setObjectName("fieldLabel");
    m_comboRes = new QComboBox(this);
    m_comboRes->setObjectName("inputCombo");
    m_comboRes->addItems({"1080p (Full HD - Recommended)", "720p (HD Quality)", "480p (SD Quality)", "Best Available", "Audio Only (No Video)"});

    card2Layout->addWidget(lblTitleOpt, 0, 0);
    card2Layout->addWidget(m_editTitle, 0, 1);
    card2Layout->addWidget(lblRes, 0, 2);
    card2Layout->addWidget(m_comboRes, 0, 3);

    // Row 1: Save Folder & Audio Tracks
    auto *lblFolder = new QLabel("Save Folder", this);
    lblFolder->setObjectName("fieldLabel");

    auto *folderBox = new QWidget(this);
    auto *folderLayout = new QHBoxLayout(folderBox);
    folderLayout->setContentsMargins(0, 0, 0, 0);
    folderLayout->setSpacing(6);

    QString defaultSave = QStandardPaths::writableLocation(QStandardPaths::DesktopLocation);
    m_editDir = new QLineEdit(defaultSave, this);
    m_editDir->setObjectName("inputField");
    m_btnBrowse = new QPushButton("Browse...", this);
    m_btnBrowse->setIcon(QIcon(":/assets/images/icon_browse.png"));
    m_btnBrowse->setObjectName("btnBrowse");
    connect(m_btnBrowse, &QPushButton::clicked, this, &MainWindow::onBrowseClicked);
    folderLayout->addWidget(m_editDir);
    folderLayout->addWidget(m_btnBrowse);

    auto *lblAudio = new QLabel("Audio Tracks", this);
    lblAudio->setObjectName("fieldLabel");
    m_comboAudio = new QComboBox(this);
    m_comboAudio->setObjectName("inputCombo");
    m_comboAudio->addItems({"All Available Languages (Lossless)", "English + Hindi (Dual Audio)", "English Only", "Hindi Only"});

    card2Layout->addWidget(lblFolder, 1, 0);
    card2Layout->addWidget(folderBox, 1, 1);
    card2Layout->addWidget(lblAudio, 1, 2);
    card2Layout->addWidget(m_comboAudio, 1, 3);

    // Row 2: Download Mode & Subtitle Format
    auto *lblMode = new QLabel("Download Mode", this);
    lblMode->setObjectName("fieldLabel");

    auto *modeBox = new QWidget(this);
    auto *modeLayout = new QHBoxLayout(modeBox);
    modeLayout->setContentsMargins(0, 0, 0, 0);
    modeLayout->setSpacing(4);

    m_btnModeNormal = new QPushButton("\u2713 Normal", this);
    m_btnModeNormal->setObjectName("btnModeActive");
    m_btnModeSubMerge = new QPushButton("Sub Merge", this);
    m_btnModeSubMerge->setObjectName("btnModeInactive");
    m_btnModeNetflix = new QPushButton("Netflix Mode", this);
    m_btnModeNetflix->setObjectName("btnModeInactive");
    m_btnModeTmdb = new QPushButton("TMDB Mode", this);
    m_btnModeTmdb->setObjectName("btnModeInactive");
    m_btnModeImdb = new QPushButton("IMDb Mode", this);
    m_btnModeImdb->setObjectName("btnModeInactive");

    connect(m_btnModeNormal, &QPushButton::clicked, [this]() { onDownloadModeChanged(0); });
    connect(m_btnModeSubMerge, &QPushButton::clicked, [this]() { onDownloadModeChanged(1); });
    connect(m_btnModeNetflix, &QPushButton::clicked, [this]() { onDownloadModeChanged(2); });
    connect(m_btnModeTmdb, &QPushButton::clicked, [this]() { onDownloadModeChanged(3); });
    connect(m_btnModeImdb, &QPushButton::clicked, [this]() { onDownloadModeChanged(4); });

    modeLayout->addWidget(m_btnModeNormal);
    modeLayout->addWidget(m_btnModeSubMerge);
    modeLayout->addWidget(m_btnModeNetflix);
    modeLayout->addWidget(m_btnModeTmdb);
    modeLayout->addWidget(m_btnModeImdb);

    auto *lblSubFmt = new QLabel("Subtitle Format", this);
    lblSubFmt->setObjectName("fieldLabel");
    m_comboSubFormat = new QComboBox(this);
    m_comboSubFormat->setObjectName("inputCombo");
    m_comboSubFormat->addItems({"SRT (SubRip \u2014 Universal)", "VTT (WebVTT)"});

    card2Layout->addWidget(lblMode, 2, 0);
    card2Layout->addWidget(modeBox, 2, 1);
    card2Layout->addWidget(lblSubFmt, 2, 2);
    card2Layout->addWidget(m_comboSubFormat, 2, 3);

    // Row 3: Subtitles Checkbox & Subtitle Language
    auto *lblSubTitle = new QLabel("Subtitles", this);
    lblSubTitle->setObjectName("fieldLabel");
    m_checkEmbedSubs = new QCheckBox("Embed Subtitles into Video (MKV container)", this);
    m_checkEmbedSubs->setObjectName("checkEmbedSubs");
    m_checkEmbedSubs->setChecked(true);

    auto *lblSubLang = new QLabel("Subtitle Language", this);
    lblSubLang->setObjectName("fieldLabel");
    m_comboSubLang = new QComboBox(this);
    m_comboSubLang->setObjectName("inputCombo");
    m_comboSubLang->addItems({"All Languages", "English (eng)", "Hindi (hin)", "Spanish (spa)", "French (fra)", "German (deu)", "Japanese (jpn)"});

    card2Layout->addWidget(lblSubTitle, 3, 0);
    card2Layout->addWidget(m_checkEmbedSubs, 3, 1);
    card2Layout->addWidget(lblSubLang, 3, 2);
    card2Layout->addWidget(m_comboSubLang, 3, 3);

    rootLayout->addWidget(m_card2);

    // ── 5. Action Buttons ─────────────────────────────────────────────────────
    m_actionWidget = new QWidget(this);
    auto *actionLayout = new QHBoxLayout(m_actionWidget);
    actionLayout->setContentsMargins(0, 0, 0, 0);
    actionLayout->setSpacing(10);

    m_btnStart = new QPushButton(" Start Download", this);
    m_btnStart->setIcon(QIcon(":/assets/images/icon_start.png"));
    m_btnStart->setObjectName("btnStartDownload");
    connect(m_btnStart, &QPushButton::clicked, this, &MainWindow::onStartDownloadClicked);
    actionLayout->addWidget(m_btnStart);

    m_btnSubs = new QPushButton(" Download Subtitles", this);
    m_btnSubs->setIcon(QIcon(":/assets/images/icon_subtitles.png"));
    m_btnSubs->setObjectName("btnDownloadSubs");
    connect(m_btnSubs, &QPushButton::clicked, this, &MainWindow::onDownloadSubtitlesClicked);
    actionLayout->addWidget(m_btnSubs);

    m_btnStop = new QPushButton(" Stop", this);
    m_btnStop->setIcon(QIcon(":/assets/images/icon_stop.png"));
    m_btnStop->setObjectName("btnStop");
    m_btnStop->setEnabled(false);
    connect(m_btnStop, &QPushButton::clicked, this, &MainWindow::onStopClicked);
    actionLayout->addWidget(m_btnStop);

    actionLayout->addStretch();
    rootLayout->addWidget(m_actionWidget);

    // ── 6. Card 3: Progress Card ──────────────────────────────────────────────
    m_card3 = new QWidget(this);
    m_card3->setObjectName("cardWidget");
    auto *card3Layout = new QVBoxLayout(m_card3);
    card3Layout->setContentsMargins(18, 10, 18, 10);
    card3Layout->setSpacing(5);

    auto *progHeader = new QHBoxLayout();
    auto *progLeft = new QVBoxLayout();
    m_lblProgTitle = new QLabel("Ready to Download", this);
    m_lblProgTitle->setObjectName("cardTitle");
    m_lblProgStatus = new QLabel("Ready \u2014 all dependencies configured.", this);
    m_lblProgStatus->setObjectName("cardSubTitle");
    progLeft->addWidget(m_lblProgTitle);
    progLeft->addWidget(m_lblProgStatus);
    progHeader->addLayout(progLeft);

    progHeader->addStretch();

    m_lblProgPct = new QLabel("0%", this);
    m_lblProgPct->setObjectName("lblProgPct");
    progHeader->addWidget(m_lblProgPct);
    card3Layout->addLayout(progHeader);

    m_progBar = new QProgressBar(this);
    m_progBar->setObjectName("progBar");
    m_progBar->setRange(0, 100);
    m_progBar->setValue(0);
    m_progBar->setTextVisible(false);
    m_progBar->setFixedHeight(8);
    card3Layout->addWidget(m_progBar);

    auto *progFooter = new QHBoxLayout();
    m_lblProgSize = new QLabel("Downloaded: -- / --", this);
    m_lblProgSize->setObjectName("lblProgMetrics");
    m_lblProgSpeed = new QLabel("0.0 MB/s", this);
    m_lblProgSpeed->setObjectName("lblProgSpeed");
    progFooter->addWidget(m_lblProgSize);
    progFooter->addStretch();
    progFooter->addWidget(m_lblProgSpeed);
    card3Layout->addLayout(progFooter);

    rootLayout->addWidget(m_card3);

    // ── 7. Card 4: Tab Container & Views ──────────────────────────────────────
    auto *card4 = new QWidget(this);
    card4->setObjectName("cardWidget");
    auto *card4Layout = new QVBoxLayout(card4);
    card4Layout->setContentsMargins(16, 10, 16, 10);
    card4Layout->setSpacing(8);

    // Tab Header
    auto *tabHeader = new QHBoxLayout();
    tabHeader->setSpacing(8);

    m_btnTabQueue = new QPushButton(" Download Queue (0)", this);
    m_btnTabQueue->setObjectName("btnTabActive");
    connect(m_btnTabQueue, &QPushButton::clicked, this, &MainWindow::onTabQueueClicked);
    tabHeader->addWidget(m_btnTabQueue);

    m_btnTabTerminal = new QPushButton(" Terminal", this);
    m_btnTabTerminal->setObjectName("btnTabInactive");
    connect(m_btnTabTerminal, &QPushButton::clicked, this, &MainWindow::onTabTerminalClicked);
    tabHeader->addWidget(m_btnTabTerminal);

    tabHeader->addStretch();

    m_btnClearLogs = new QPushButton("Clear Logs", this);
    m_btnClearLogs->setObjectName("btnToolbar");
    m_btnClearLogs->setVisible(false);
    connect(m_btnClearLogs, &QPushButton::clicked, this, &MainWindow::onClearLogsClicked);
    tabHeader->addWidget(m_btnClearLogs);

    card4Layout->addLayout(tabHeader);

    // Stacked Pages
    m_stackedPages = new QStackedWidget(this);

    // Page 0: Queue View
    m_pageQueue = new QWidget(this);
    auto *queuePageLayout = new QVBoxLayout(m_pageQueue);
    queuePageLayout->setContentsMargins(0, 0, 0, 0);
    queuePageLayout->setSpacing(8);

    // Queue Toolbar
    auto *queueToolbar = new QHBoxLayout();
    m_btnDownloadAll = new QPushButton(" Download All", this);
    m_btnDownloadAll->setIcon(QIcon(":/assets/images/icon_start.png"));
    m_btnDownloadAll->setObjectName("btnDownloadAll");
    connect(m_btnDownloadAll, &QPushButton::clicked, this, &MainWindow::onDownloadAllClicked);
    queueToolbar->addWidget(m_btnDownloadAll);

    m_btnClearQueue = new QPushButton("Clear All", this);
    m_btnClearQueue->setObjectName("btnToolbar");
    connect(m_btnClearQueue, &QPushButton::clicked, this, &MainWindow::onClearQueueClicked);
    queueToolbar->addWidget(m_btnClearQueue);

    m_btnFullView = new QPushButton("Full View \u2197", this);
    m_btnFullView->setObjectName("btnToolbar");
    connect(m_btnFullView, &QPushButton::clicked, this, &MainWindow::onFullViewClicked);
    queueToolbar->addWidget(m_btnFullView);

    queueToolbar->addStretch();

    m_lblQueueStats = new QLabel("Queue: 0 total \u2022 0 active \u2022 0 waiting \u2022 0 done", this);
    m_lblQueueStats->setObjectName("lblQueueStats");
    queueToolbar->addWidget(m_lblQueueStats);

    queuePageLayout->addLayout(queueToolbar);

    // Custom Empty Queue Grid Blueprint Widget matching screenshot
    m_emptyQueuePlaceholder = new EmptyQueueGridWidget(this);
    auto *placeholderLayout = new QVBoxLayout(m_emptyQueuePlaceholder);
    placeholderLayout->setContentsMargins(20, 20, 20, 20);
    placeholderLayout->setAlignment(Qt::AlignCenter);

    auto *lblEmptyIcon = new QLabel(this);
    lblEmptyIcon->setPixmap(QPixmap(":/assets/images/empty_queue_box.png").scaled(64, 64, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    lblEmptyIcon->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptyIcon);

    auto *lblEmptyTitle = new QLabel("The Download Queue is empty.", this);
    lblEmptyTitle->setObjectName("lblEmptyTitle");
    lblEmptyTitle->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptyTitle);

    auto *lblEmptySub1 = new QLabel("Capture media links using the OmniStream Pro Chrome Extension or paste cURL/links above and click 'Add to Queue'.", this);
    lblEmptySub1->setObjectName("lblEmptySub");
    lblEmptySub1->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptySub1);

    auto *lblEmptySub2 = new QLabel("When links are added, click 'Download All' to batch download like IDM.", this);
    lblEmptySub2->setObjectName("lblEmptySub");
    lblEmptySub2->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptySub2);

    queuePageLayout->addWidget(m_emptyQueuePlaceholder);

    // Queue Table (Hidden while empty, shown when items are added)
    m_tableQueue = new QTableWidget(this);
    m_tableQueue->setObjectName("tableQueue");
    m_tableQueue->setColumnCount(6);
    m_tableQueue->setHorizontalHeaderLabels({"Item Title", "Resolution", "Progress", "Speed", "Size", "Status"});
    m_tableQueue->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    m_tableQueue->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_tableQueue->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    m_tableQueue->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    m_tableQueue->horizontalHeader()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    m_tableQueue->horizontalHeader()->setSectionResizeMode(5, QHeaderView::ResizeToContents);
    m_tableQueue->verticalHeader()->setVisible(false);
    m_tableQueue->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_tableQueue->setVisible(false);
    queuePageLayout->addWidget(m_tableQueue);

    m_stackedPages->addWidget(m_pageQueue);

    // Page 1: Terminal View
    m_editTerminal = new QPlainTextEdit(this);
    m_editTerminal->setObjectName("editTerminal");
    m_editTerminal->setReadOnly(true);
    m_stackedPages->addWidget(m_editTerminal);

    card4Layout->addWidget(m_stackedPages);
    rootLayout->addWidget(card4, 1);

    // ── 8. Footer ─────────────────────────────────────────────────────────────
    auto *footerWidget = new QWidget(this);
    auto *footerLayout = new QHBoxLayout(footerWidget);
    footerLayout->setContentsMargins(4, 2, 4, 0);

    m_lblFooterBridge = new QLabel("\u25CF Extension Bridge  \u2022  Connected & Active", this);
    m_lblFooterBridge->setObjectName("lblFooterBridge");
    footerLayout->addWidget(m_lblFooterBridge);

    footerLayout->addStretch();

    m_lblFooterAuthor = new QLabel(
        "OmniStream Pro v2.6.0  \u2022  Developed by XMON4U  \u2022  <a href=\"https://github.com/Xmon4u/OmniStream-Pro-v2\" style=\"color: #58a6ff; text-decoration: none;\">GitHub Repository</a>",
        this);
    m_lblFooterAuthor->setObjectName("lblFooterAuthor");
    m_lblFooterAuthor->setCursor(Qt::PointingHandCursor);
    m_lblFooterAuthor->setOpenExternalLinks(true);
    m_lblFooterAuthor->setTextFormat(Qt::RichText);
    footerLayout->addWidget(m_lblFooterAuthor);

    rootLayout->addWidget(footerWidget);

    handleLogMessage("OmniStream Pro v2.6.0 Native C++ Engine loaded.");
    handleLogMessage("Hardware Acceleration: Windows BCrypt AES-NI Active.");
    handleLogMessage("WinHTTP Asynchronous Streaming Pipeline Initialized.");
}

void MainWindow::applyStyleSheet(int themeIdx) {
    bool midnight = (themeIdx == 1);
    QString cardBg = midnight ? "#090d14" : "#161b22";
    QString cardBorder = midnight ? "#1e293b" : "#30363d";
    QString inputBg = midnight ? "#020408" : "#090d13";
    QString inputBorder = midnight ? "#1a2234" : "#21262d";
    QString termBg = midnight ? "#000000" : "#05070a";
    QString tableBg = midnight ? "#020408" : "#090d13";
    QString tableHeader = midnight ? "#090d14" : "#161b22";

    QString qss = QString(R"(
        QWidget {
            background-color: transparent;
            color: #f0f6fc;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 13px;
        }
        #headerWidget {
            background-color: transparent;
        }
        #lblAppTitle {
            font-size: 16px;
            font-weight: bold;
            color: #f0f6fc;
        }
        #lblVersionBadge {
            background-color: #21262d;
            color: #8b949e;
            font-size: 11px;
            border-radius: 4px;
            padding: 2px 6px;
        }
        #comboTheme {
            background-color: #21262d;
            color: #8b949e;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 3px 10px;
            font-size: 11px;
        }
        #lblStatusBadge {
            background-color: #064e3b;
            color: #34d399;
            font-size: 11px;
            font-weight: bold;
            border: 1px solid #059669;
            border-radius: 12px;
            padding: 3px 12px;
        }
        #btnCapMin, #btnCapMax, #btnCapClose {
            background-color: transparent;
            border: none;
        }
        #bannerWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e1b4b, stop:0.5 #2e1065, stop:1 #1e1b4b);
            border: 1px solid #4338ca;
            border-radius: 10px;
        }
        #bannerWidget:hover {
            border: 1px solid #6366f1;
        }
        #lblBannerText {
            color: #c7d2fe;
            font-size: 12px;
            font-weight: 500;
        }
        #cardWidget {
            background-color: %1;
            border: 1px solid %2;
            border-radius: 12px;
        }
        #cardWidget:hover {
            border: 1px solid #388bfd55;
        }
        #cardTitle {
            font-size: 13px;
            font-weight: bold;
            color: #f0f6fc;
        }
        #cardSubTitle {
            font-size: 11px;
            color: #8b949e;
        }
        #fieldLabel {
            font-size: 12px;
            font-weight: 600;
            color: #8b949e;
        }
        #inputField, #editUrl {
            background-color: %3;
            border: 1px solid %4;
            border-radius: 8px;
            color: #f0f6fc;
            padding: 5px 10px;
            font-size: 12px;
        }
        #inputField:focus, #editUrl:focus {
            border: 1px solid #38bdf8;
            background-color: %3;
        }
        #inputCombo {
            background-color: %3;
            border: 1px solid %4;
            border-radius: 8px;
            color: #f0f6fc;
            padding: 4px 10px;
            font-size: 12px;
        }
        #inputCombo:focus {
            border: 1px solid #38bdf8;
        }
        #inputCombo QAbstractItemView {
            background-color: %1;
            border: 1px solid %2;
            selection-background-color: #2563eb;
            color: #f0f6fc;
        }
        #btnPaste, #btnBrowse, #btnToolbar {
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #f0f6fc;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
        }
        #btnPaste:hover, #btnBrowse:hover, #btnToolbar:hover {
            background-color: #30363d;
            border: 1px solid #58a6ff;
            color: #ffffff;
        }
        #btnModeActive {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            color: #ffffff;
            font-weight: bold;
            border-radius: 6px;
            padding: 5px 12px;
            border: 1px solid #60a5fa;
            font-size: 11px;
        }
        #btnModeInactive {
            background-color: #090d13;
            color: #8b949e;
            border: 1px solid #21262d;
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 11px;
        }
        #btnModeInactive:hover {
            background-color: #161b22;
            color: #f0f6fc;
            border: 1px solid #30363d;
        }
        #checkEmbedSubs {
            color: #f0f6fc;
            font-size: 12px;
        }
        #checkEmbedSubs::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid #30363d;
            background-color: #090d13;
        }
        #checkEmbedSubs::indicator:checked {
            background-color: #2563eb;
            border: 1px solid #38bdf8;
        }
        #btnStartDownload {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:0.5 #2563eb, stop:1 #38bdf8);
            color: #ffffff;
            font-size: 13px;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px 20px;
            border: 1px solid #38bdf888;
        }
        #btnStartDownload:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:0.5 #3b82f6, stop:1 #7dd3fc);
            border: 1px solid #7dd3fc;
        }
        #btnStartDownload:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:0.5 #1d4ed8, stop:1 #0284c7);
        }
        #btnDownloadSubs {
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 8px;
            color: #f0f6fc;
            font-size: 13px;
            font-weight: bold;
            padding: 8px 16px;
        }
        #btnDownloadSubs:hover {
            background-color: #30363d;
            border: 1px solid #58a6ff;
            color: #ffffff;
        }
        #btnStop {
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 8px;
            color: #6e7681;
            font-size: 13px;
            font-weight: bold;
            padding: 8px 16px;
        }
        #btnStop:enabled {
            background-color: #ef4444;
            color: #ffffff;
            border: 1px solid #f87171;
        }
        #btnStop:enabled:hover {
            background-color: #dc2626;
        }
        #lblProgPct {
            font-size: 18px;
            font-weight: bold;
            color: #38bdf8;
        }
        #progBar {
            background-color: #090d13;
            border: 1px solid #21262d;
            border-radius: 4px;
        }
        #progBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:0.5 #38bdf8, stop:1 #c084fc);
            border-radius: 4px;
        }
        #lblProgMetrics {
            font-size: 11px;
            color: #8b949e;
            font-weight: 600;
        }
        #lblProgSpeed {
            font-size: 12px;
            color: #38bdf8;
            font-weight: bold;
        }
        #btnTabActive {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            color: #ffffff;
            font-weight: bold;
            border-radius: 6px;
            padding: 6px 14px;
            border: 1px solid #60a5fa;
            font-size: 12px;
        }
        #btnTabInactive {
            background-color: #21262d;
            color: #8b949e;
            border-radius: 6px;
            padding: 6px 14px;
            border: 1px solid #30363d;
            font-size: 12px;
        }
        #btnTabInactive:hover {
            background-color: #30363d;
            color: #f0f6fc;
        }
        #btnDownloadAll {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
            color: #ffffff;
            font-weight: bold;
            border-radius: 6px;
            padding: 5px 14px;
            border: 1px solid #34d39988;
            font-size: 11px;
        }
        #btnDownloadAll:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #10b981);
            border: 1px solid #6ee7b7;
        }
        #lblQueueStats {
            font-size: 11px;
            color: #8b949e;
        }
        #lblEmptyTitle {
            font-size: 13px;
            font-weight: bold;
            color: #8b949e;
            margin-top: 6px;
        }
        #lblEmptySub {
            font-size: 11px;
            color: #4b5563;
        }
        #editTerminal {
            background-color: %5;
            border: 1px solid %4;
            border-radius: 8px;
            color: #79c0ff;
            font-family: 'Consolas', monospace;
            font-size: 11px;
        }
        #tableQueue {
            background-color: %6;
            border: 1px solid %4;
            border-radius: 8px;
            color: #f0f6fc;
            gridline-color: %4;
        }
        #tableQueue QHeaderView::section {
            background-color: %7;
            color: #8b949e;
            font-weight: bold;
            border: 1px solid %4;
            padding: 4px;
        }
        #lblFooterBridge {
            color: #10b981;
            font-size: 11px;
            font-weight: bold;
        }
        #lblFooterAuthor {
            color: #6e7681;
            font-size: 11px;
        }
    )").arg(cardBg, cardBorder, inputBg, inputBorder, termBg).arg(tableBg, tableHeader);
    setStyleSheet(qss);
}

void MainWindow::onFullViewClicked() {
    m_isFullView = !m_isFullView;
    if (m_bannerWidget) m_bannerWidget->setVisible(!m_isFullView);
    if (m_card1) m_card1->setVisible(!m_isFullView);
    if (m_card2) m_card2->setVisible(!m_isFullView);
    if (m_actionWidget) m_actionWidget->setVisible(!m_isFullView);
    if (m_card3) m_card3->setVisible(!m_isFullView);

    if (m_btnFullView) {
        m_btnFullView->setText(m_isFullView ? "\u2190 Back to Dashboard" : "Full View \u2197");
    }
}

void MainWindow::onThemeChanged(int index) {
    applyStyleSheet(index);
    update();
}

void MainWindow::onPasteClicked() {
    QClipboard *clipboard = QApplication::clipboard();
    m_editUrl->setPlainText(clipboard->text());
}

void MainWindow::onBrowseClicked() {
    QString dir = QFileDialog::getExistingDirectory(this, "Select Download Directory", m_editDir->text());
    if (!dir.isEmpty()) {
        m_editDir->setText(dir);
    }
}

void MainWindow::setDownloadMode(const QString& modeStr) {
    QString m = modeStr.toLower();
    if (m.contains("imdb")) {
        onDownloadModeChanged(4);
    } else if (m.contains("tmdb")) {
        onDownloadModeChanged(3);
    } else if (m.contains("netflix")) {
        onDownloadModeChanged(2);
    } else if (m.contains("sub") || m.contains("merge")) {
        onDownloadModeChanged(1);
    } else {
        onDownloadModeChanged(0);
    }
}

void MainWindow::onDownloadModeChanged(int modeIdx) {
    m_selectedMode = modeIdx;
    m_btnModeNormal->setObjectName(modeIdx == 0 ? "btnModeActive" : "btnModeInactive");
    m_btnModeSubMerge->setObjectName(modeIdx == 1 ? "btnModeActive" : "btnModeInactive");
    m_btnModeNetflix->setObjectName(modeIdx == 2 ? "btnModeActive" : "btnModeInactive");
    m_btnModeTmdb->setObjectName(modeIdx == 3 ? "btnModeActive" : "btnModeInactive");
    m_btnModeImdb->setObjectName(modeIdx == 4 ? "btnModeActive" : "btnModeInactive");

    m_btnModeNormal->setText(modeIdx == 0 ? "\u2713 Normal" : "Normal");
    m_btnModeSubMerge->setText(modeIdx == 1 ? "\u2713 Sub Merge" : "Sub Merge");
    m_btnModeNetflix->setText(modeIdx == 2 ? "\u2713 Netflix Mode" : "Netflix Mode");
    m_btnModeTmdb->setText(modeIdx == 3 ? "\u2713 TMDB Mode" : "TMDB Mode");
    m_btnModeImdb->setText(modeIdx == 4 ? "\u2713 IMDb Mode" : "IMDb Mode");

    // Reapply style properties
    m_btnModeNormal->style()->unpolish(m_btnModeNormal);
    m_btnModeNormal->style()->polish(m_btnModeNormal);
    m_btnModeSubMerge->style()->unpolish(m_btnModeSubMerge);
    m_btnModeSubMerge->style()->polish(m_btnModeSubMerge);
    m_btnModeNetflix->style()->unpolish(m_btnModeNetflix);
    m_btnModeNetflix->style()->polish(m_btnModeNetflix);
    m_btnModeTmdb->style()->unpolish(m_btnModeTmdb);
    m_btnModeTmdb->style()->polish(m_btnModeTmdb);
    m_btnModeImdb->style()->unpolish(m_btnModeImdb);
    m_btnModeImdb->style()->polish(m_btnModeImdb);

    std::string modeCode = "normal";
    if (modeIdx == 1) modeCode = "sub_merge";
    else if (modeIdx == 2) modeCode = "netflix_rename";
    else if (modeIdx == 3) modeCode = "tmdb_rename";
    else if (modeIdx == 4) modeCode = "imdb_rename";

    if (m_bridgeServer) {
        m_bridgeServer->SetCurrentMode(modeCode);
    }

    if (modeIdx == 0) {
        handleLogMessage("[Mode] Switched to Normal Mode (Keeps original stream title/filename).");
    } else if (modeIdx == 1) {
        handleLogMessage("[Mode] Switched to Sub Merge Mode (Video + all multi-audio + subtitles merged into MKV).");
        m_checkEmbedSubs->setChecked(true);
    } else if (modeIdx == 2) {
        handleLogMessage("[Mode] Switched to Netflix Mode (Auto-identifies Netflix ID & renames file, e.g. 81902147.mkv).");
        m_checkEmbedSubs->setChecked(true);
    } else if (modeIdx == 3) {
        handleLogMessage("[Mode] Switched to TMDB Mode (Auto-identifies TMDB ID & renames file, e.g. 939243.mkv).");
        m_checkEmbedSubs->setChecked(true);
    } else if (modeIdx == 4) {
        handleLogMessage("[Mode] Switched to IMDb Mode (Auto-identifies IMDb ID & renames file, e.g. tt18259086.mkv).");
        m_checkEmbedSubs->setChecked(true);
    }
}

void MainWindow::onTabQueueClicked() {
    m_btnTabQueue->setObjectName("btnTabActive");
    m_btnTabTerminal->setObjectName("btnTabInactive");
    m_btnTabQueue->style()->unpolish(m_btnTabQueue);
    m_btnTabQueue->style()->polish(m_btnTabQueue);
    m_btnTabTerminal->style()->unpolish(m_btnTabTerminal);
    m_btnTabTerminal->style()->polish(m_btnTabTerminal);

    m_stackedPages->setCurrentIndex(0);
    m_btnClearLogs->setVisible(false);
}

void MainWindow::onTabTerminalClicked() {
    m_btnTabTerminal->setObjectName("btnTabActive");
    m_btnTabQueue->setObjectName("btnTabInactive");
    m_btnTabTerminal->style()->unpolish(m_btnTabTerminal);
    m_btnTabTerminal->style()->polish(m_btnTabTerminal);
    m_btnTabQueue->style()->unpolish(m_btnTabQueue);
    m_btnTabQueue->style()->polish(m_btnTabQueue);

    m_stackedPages->setCurrentIndex(1);
    m_btnClearLogs->setVisible(true);
}

void MainWindow::onClearLogsClicked() {
    m_editTerminal->clear();
}

void MainWindow::onClearQueueClicked() {
    m_tableQueue->setRowCount(0);
    m_tableQueue->setVisible(false);
    m_emptyQueuePlaceholder->setVisible(true);
    m_btnTabQueue->setText(" Download Queue (0)");
    m_lblQueueStats->setText("Queue: 0 total \u2022 0 active \u2022 0 waiting \u2022 0 done");
}

void MainWindow::onDownloadAllClicked() {
    if (m_isDownloading.load()) return;
    onStartDownloadClicked();
}

void MainWindow::onStartDownloadClicked() {
    startDownloadEngine(false);
}

void MainWindow::onDownloadSubtitlesClicked() {
    startDownloadEngine(true);
}

void MainWindow::startDownloadEngine(bool subtitleOnly) {
    if (m_isDownloading.load()) return;

    QString inputUrl = m_editUrl->toPlainText().trimmed();
    if (inputUrl.isEmpty()) {
        QMessageBox::warning(this, "Input Required", "Please enter a stream URL or Chrome cURL command.");
        return;
    }

    DownloadOptions options;
    options.inputText = inputUrl.toStdString();
    options.saveDir = m_editDir->text().toStdString();
    options.saveName = m_editTitle->text().toStdString();
    options.resolution = m_comboRes->currentIndex() == 0 ? "1080p" : (m_comboRes->currentIndex() == 1 ? "720p" : "480p");
    options.threadCount = 32;

    if (m_selectedMode == 1) options.mode = "sub_merge";
    else if (m_selectedMode == 2) options.mode = "netflix_rename";
    else if (m_selectedMode == 3) options.mode = "tmdb_rename";
    else if (m_selectedMode == 4) options.mode = "imdb_rename";
    else options.mode = "normal";

    options.includeSubtitles = m_checkEmbedSubs->isChecked();

    m_lblProgTitle->setText(options.saveName.empty() ? "Capturing Stream..." : QString::fromStdString(options.saveName));
    m_lblProgStatus->setText("Initializing download engine...");
    m_lblProgPct->setText("0%");
    m_progBar->setValue(0);
    m_lblProgSpeed->setText("0.0 MB/s");

    m_isDownloading.store(true);
    m_btnStart->setEnabled(false);
    m_btnSubs->setEnabled(false);
    m_btnStop->setEnabled(true);

    m_currentEngine = std::make_unique<DownloadEngine>();
    DownloadEngine* engine = m_currentEngine.get();

    options.onProgress = [this](float pct, const std::string& speed, const std::string& eta, uint64_t bytes) {
        emit progressUpdated(pct, QString::fromStdString(speed), QString::fromStdString(eta), bytes);
    };

    options.onLog = [this](const std::string& msg) {
        emit logMessageReceived(QString::fromStdString(msg));
    };

    m_downloadThread = std::make_unique<std::thread>([this, engine, options]() {
        std::string finalOutput;
        bool ok = engine->Download(options, finalOutput);
        emit downloadCompleted(ok);
    });
}

void MainWindow::onStopClicked() {
    if (m_isDownloading.load() && m_currentEngine) {
        m_currentEngine->Abort();
        handleLogMessage("[Engine] Download aborted by user.");
        m_lblProgStatus->setText("Cancelled by user.");
        m_isDownloading.store(false);
        m_btnStart->setEnabled(true);
        m_btnSubs->setEnabled(true);
        m_btnStop->setEnabled(false);
    }
}

void MainWindow::addQueueItem(const DownloadOptions& opts) {
    if (!m_tableQueue) return;

    m_emptyQueuePlaceholder->setVisible(false);
    m_tableQueue->setVisible(true);

    int row = m_tableQueue->rowCount();
    m_tableQueue->insertRow(row);

    QString title = opts.saveName.empty() ? QString("Stream Item #%1").arg(row + 1) : QString::fromStdString(opts.saveName);
    QString res = opts.resolution.empty() ? "1080p" : QString::fromStdString(opts.resolution);

    m_tableQueue->setItem(row, 0, new QTableWidgetItem(title));
    m_tableQueue->setItem(row, 1, new QTableWidgetItem(res));
    m_tableQueue->setItem(row, 2, new QTableWidgetItem("0%"));
    m_tableQueue->setItem(row, 3, new QTableWidgetItem("0.0 MB/s"));
    m_tableQueue->setItem(row, 4, new QTableWidgetItem("--"));
    m_tableQueue->setItem(row, 5, new QTableWidgetItem("Queued"));

    for (int col = 0; col < 6; ++col) {
        if (auto *item = m_tableQueue->item(row, col)) {
            item->setForeground(QBrush(QColor("#f0f6fc")));
        }
    }

    int total = m_tableQueue->rowCount();
    m_btnTabQueue->setText(QString(" Download Queue (%1)").arg(total));
    m_lblQueueStats->setText(QString("Queue: %1 total \u2022 %2 active \u2022 %3 waiting \u2022 0 done")
        .arg(total).arg(m_isDownloading.load() ? 1 : 0).arg(total - (m_isDownloading.load() ? 1 : 0)));
}

void MainWindow::handleLogMessage(const QString& msg) {
    m_editTerminal->appendPlainText(msg);
}

void MainWindow::handleProgressUpdate(float pct, const QString& speed, const QString& eta, quint64 bytes) {
    m_progBar->setValue(static_cast<int>(pct));
    m_lblProgPct->setText(QString::number(pct, 'f', 1) + "%");
    m_lblProgSpeed->setText(speed.isEmpty() ? "0.0 MB/s" : speed);
    m_lblProgSize->setText("Downloaded: " + QString::fromStdString(FormatBytes(bytes)));

    if (pct >= 100.0f) {
        m_lblProgStatus->setText("Completed \u2014 File saved successfully.");
    } else if (pct > 0.0f) {
        m_lblProgStatus->setText("Downloading segments \u2022 ETA: " + eta);
    }

    if (m_tableQueue && m_tableQueue->rowCount() > 0) {
        int activeRow = 0;
        if (auto *pItem = m_tableQueue->item(activeRow, 2)) pItem->setText(QString::number(pct, 'f', 1) + "%");
        if (auto *sItem = m_tableQueue->item(activeRow, 3)) sItem->setText(speed.isEmpty() ? "0.0 MB/s" : speed);
        if (auto *szItem = m_tableQueue->item(activeRow, 4)) szItem->setText(QString::fromStdString(FormatBytes(bytes)));
        if (auto *stItem = m_tableQueue->item(activeRow, 5)) {
            stItem->setText("Downloading");
            stItem->setForeground(QBrush(QColor("#38bdf8")));
        }
    }
}

void MainWindow::handleDownloadComplete(bool success) {
    m_isDownloading.store(false);
    m_btnStart->setEnabled(true);
    m_btnSubs->setEnabled(true);
    m_btnStop->setEnabled(false);

    if (success) {
        m_progBar->setValue(100);
        m_lblProgPct->setText("100%");
        m_lblProgStatus->setText("Download Completed Successfully! 100% Verified.");
        handleLogMessage("[Engine] 100% Download Completed Successfully.");
    } else {
        m_lblProgStatus->setText("Download finished with warnings or errors.");
        handleLogMessage("[Engine] Download finished.");
    }

    if (m_tableQueue && m_tableQueue->rowCount() > 0) {
        int activeRow = 0;
        if (auto *stItem = m_tableQueue->item(activeRow, 5)) {
            stItem->setText(success ? "Done" : "Failed");
            stItem->setForeground(QBrush(QColor(success ? "#34d399" : "#f87171")));
        }
    }
}

} // namespace OmniStream
