#include "MainWindow.h"
#include "SettingsDialog.h"
#include "ExtensionInstaller.hpp"
#include <QApplication>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QGridLayout>
#include <QHeaderView>
#include <QScrollBar>
#include <QFileDialog>
#include <QClipboard>
#include <QProcess>
#include <fstream>
#include <sstream>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <windowsx.h>

namespace OmniStream {

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent) {
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinMaxButtonsHint);
    setAttribute(Qt::WA_TranslucentBackground, false);
    setMinimumSize(1080, 780);
    resize(1160, 840);
    m_normalGeometry = geometry();

    setupUI();
    setupSystemTray();
    applyStyleSheet(0); // Default to Cyber Slate

    // Connect QueueManager backend events
    QueueManager::GetInstance().SetQueueChangedCallback([this]() {
        QMetaObject::invokeMethod(this, "onBackendQueueChanged", Qt::QueuedConnection);
    });

    QueueManager::GetInstance().SetItemUpdatedCallback([this](const DownloadItem& item) {
        QMetaObject::invokeMethod(this, [this, item]() {
            onBackendItemUpdated(item);
        }, Qt::QueuedConnection);
    });

    QueueManager::GetInstance().SetLogCallback([this](const std::string& msg) {
        QMetaObject::invokeMethod(this, [this, msg]() {
            onBackendLogMessage(QString::fromStdString(msg));
        }, Qt::QueuedConnection);
    });

    QueueManager::GetInstance().SetModeChangedCallback([this](DownloadMode mode) {
        QMetaObject::invokeMethod(this, [this, mode]() {
            int modeIdx = static_cast<int>(mode);
            if (m_selectedMode != modeIdx) {
                m_selectedMode = modeIdx;
                std::vector<std::pair<QPushButton*, QString>> btns = {
                    { m_btnModeNormal, "Normal" },
                    { m_btnModeNetflix, "Netflix" },
                    { m_btnModeTitleOnly, "Title Only" },
                    { m_btnModeImdb, "IMDb" },
                    { m_btnModeTmdb, "TMDB" },
                    { m_btnModeTitleId, "T+ID" },
                    { m_btnModeSubMerge, "Sub Merge" },
                    { m_btnModeAuto, "Auto" }
                };
                for (size_t i = 0; i < btns.size(); ++i) {
                    if (btns[i].first) {
                        bool isActive = (static_cast<int>(i) == modeIdx);
                        btns[i].first->setObjectName(isActive ? "btnModeActive" : "btnModeInactive");
                        btns[i].first->setText(isActive ? ("✓ " + btns[i].second) : btns[i].second);
                    }
                }
                applyStyleSheet(m_currentTheme);
            }
        }, Qt::QueuedConnection);
    });

    rebuildQueueCards();
    updateQueueStats();
}

MainWindow::~MainWindow() {
    QueueManager::GetInstance().SetQueueChangedCallback(nullptr);
    QueueManager::GetInstance().SetItemUpdatedCallback(nullptr);
    QueueManager::GetInstance().SetModeChangedCallback(nullptr);
    QueueManager::GetInstance().SetLogCallback(nullptr);
}

bool MainWindow::nativeEvent(const QByteArray &eventType, void *message, qintptr *result) {
    if (eventType == "windows_generic_MSG" && message) {
        MSG *msg = static_cast<MSG*>(message);
        HWND hwnd = msg->hwnd;
        if (!hwnd) {
            return QMainWindow::nativeEvent(eventType, message, result);
        }

        if (msg->message == WM_NCHITTEST) {
            POINT pt = { GET_X_LPARAM(msg->lParam), GET_Y_LPARAM(msg->lParam) };
            RECT winRect;
            if (GetWindowRect(hwnd, &winRect)) {
                int x = pt.x - winRect.left;
                int y = pt.y - winRect.top;
                int w = winRect.right - winRect.left;
                int h = winRect.bottom - winRect.top;

                // Border resizing margins (only when not maximized)
                if (!isMaximized()) {
                    const int border = 8;
                    bool left = (x < border);
                    bool right = (x >= w - border);
                    bool top = (y < border);
                    bool bottom = (y >= h - border);

                    if (top && left) { *result = HTTOPLEFT; return true; }
                    if (top && right) { *result = HTTOPRIGHT; return true; }
                    if (bottom && left) { *result = HTBOTTOMLEFT; return true; }
                    if (bottom && right) { *result = HTBOTTOMRIGHT; return true; }
                    if (left) { *result = HTLEFT; return true; }
                    if (right) { *result = HTRIGHT; return true; }
                    if (top) { *result = HTTOP; return true; }
                    if (bottom) { *result = HTBOTTOM; return true; }
                }

                // Top caption bar for moving / snapping (height 44px)
                if (y <= 44) {
                    // The rightmost 380px contain Settings, Theme combo, and caption buttons
                    if (x < w - 380) {
                        *result = HTCAPTION;
                        return true;
                    }
                }
            }
        }
        else if (msg->message == WM_GETMINMAXINFO) {
            MINMAXINFO *mmi = reinterpret_cast<MINMAXINFO*>(msg->lParam);
            if (mmi) {
                HMONITOR hMon = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
                if (hMon) {
                    MONITORINFO mi = { sizeof(mi) };
                    if (GetMonitorInfoW(hMon, &mi)) {
                        mmi->ptMaxPosition.x = mi.rcWork.left - mi.rcMonitor.left;
                        mmi->ptMaxPosition.y = mi.rcWork.top - mi.rcMonitor.top;
                        mmi->ptMaxSize.x = mi.rcWork.right - mi.rcWork.left;
                        mmi->ptMaxSize.y = mi.rcWork.bottom - mi.rcWork.top;
                    }
                }
                mmi->ptMinTrackSize.x = 1080;
                mmi->ptMinTrackSize.y = 720;
                *result = 0;
                return true;
            }
        }
    }
    return QMainWindow::nativeEvent(eventType, message, result);
}

void MainWindow::changeEvent(QEvent *event) {
    if (event->type() == QEvent::WindowStateChange) {
        bool max = isMaximized();
        if (m_btnCapMax) {
            m_btnCapMax->setMaximizedState(max);
        }
    }
    QMainWindow::changeEvent(event);
}

void MainWindow::resizeEvent(QResizeEvent* event) {
    if (!isMaximized() && !isMinimized()) {
        m_normalGeometry = geometry();
    }
    QMainWindow::resizeEvent(event);
}

void MainWindow::moveEvent(QMoveEvent* event) {
    if (!isMaximized() && !isMinimized()) {
        m_normalGeometry = geometry();
    }
    QMainWindow::moveEvent(event);
}

void MainWindow::closeEvent(QCloseEvent* event) {
    if (SettingsManager::GetInstance().GetSettings().minimize_to_tray_on_close) {
        hide();
        event->ignore();
        if (m_trayIcon && m_trayIcon->isVisible()) {
            m_trayIcon->showMessage("OmniStream Pro", "Minimized to tray. Continuing stream capture in background.", QSystemTrayIcon::Information, 1500);
        }
    } else {
        event->accept();
    }
}

void MainWindow::setupSystemTray() {
    m_trayIcon = new QSystemTrayIcon(QIcon(":/assets/images/app_logo.png"), this);
    auto *trayMenu = new QMenu(this);

    auto *actOpen = trayMenu->addAction("Open OmniStream Pro");
    connect(actOpen, &QAction::triggered, [this]() {
        showNormal();
        activateWindow();
    });

    trayMenu->addSeparator();

    auto *actDlAll = trayMenu->addAction("Download All");
    connect(actDlAll, &QAction::triggered, this, &MainWindow::onDownloadAllClicked);

    auto *actPauseAll = trayMenu->addAction("Pause All");
    connect(actPauseAll, &QAction::triggered, this, &MainWindow::onPauseAllClicked);

    trayMenu->addSeparator();

    auto *actQuit = trayMenu->addAction("Exit OmniStream Pro");
    connect(actQuit, &QAction::triggered, [this]() {
        SettingsManager::GetInstance().GetSettings().minimize_to_tray_on_close = false;
        QApplication::quit();
    });

    m_trayIcon->setContextMenu(trayMenu);
    m_trayIcon->setToolTip("OmniStream Pro v2.6.0");

    connect(m_trayIcon, &QSystemTrayIcon::activated, [this](QSystemTrayIcon::ActivationReason reason) {
        if (reason == QSystemTrayIcon::Trigger || reason == QSystemTrayIcon::DoubleClick) {
            if (isVisible()) {
                hide();
            } else {
                showNormal();
                activateWindow();
            }
        }
    });

    m_trayIcon->show();
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event) {
    if (watched == m_bannerWidget && event->type() == QEvent::MouseButtonRelease) {
        onSetupExtensionClicked();
        return true;
    }
    return QMainWindow::eventFilter(watched, event);
}

void MainWindow::setupUI() {
    auto *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    auto *rootLayout = new QVBoxLayout(centralWidget);
    rootLayout->setContentsMargins(20, 12, 20, 12);
    rootLayout->setSpacing(10);

    // ── 1. Top Integrated Header ──────────────────────────────────────────────
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

    // Preferences / Settings button
    m_btnSettings = new QPushButton("⚙ Settings", this);
    m_btnSettings->setObjectName("btnToolbar");
    m_btnSettings->setCursor(Qt::PointingHandCursor);
    connect(m_btnSettings, &QPushButton::clicked, this, &MainWindow::onOpenSettingsClicked);
    headerLayout->addWidget(m_btnSettings);

    m_comboTheme = new QComboBox(this);
    m_comboTheme->setObjectName("comboTheme");
    m_comboTheme->addItem("Cyber Slate");
    m_comboTheme->addItem("Midnight Black");
    connect(m_comboTheme, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::onThemeChanged);
    headerLayout->addWidget(m_comboTheme);

    m_lblStatusBadge = new QLabel("● Ready", this);
    m_lblStatusBadge->setObjectName("lblStatusBadge");
    headerLayout->addWidget(m_lblStatusBadge);

    // Caption Buttons
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
            if (!m_normalGeometry.isEmpty()) {
                setGeometry(m_normalGeometry);
            }
            m_btnCapMax->setMaximizedState(false);
        } else {
            m_normalGeometry = geometry();
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
    m_bannerWidget->setCursor(Qt::PointingHandCursor);
    m_bannerWidget->installEventFilter(this);

    auto *bannerLayout = new QHBoxLayout(m_bannerWidget);
    bannerLayout->setContentsMargins(16, 6, 12, 6);
    bannerLayout->setSpacing(10);

    auto *lblBannerText = new QLabel("● Chrome Extension Bridge Active — Ready for 1-Click Stream Capture", this);
    lblBannerText->setObjectName("lblBannerText");
    lblBannerText->setCursor(Qt::PointingHandCursor);
    bannerLayout->addWidget(lblBannerText);
    bannerLayout->addStretch();

    m_btnSetupExtension = new QPushButton("⚡ Setup Extension (1-Click)", this);
    m_btnSetupExtension->setObjectName("btnBannerSetup");
    m_btnSetupExtension->setCursor(Qt::PointingHandCursor);
    connect(m_btnSetupExtension, &QPushButton::clicked, this, &MainWindow::onSetupExtensionClicked);
    bannerLayout->addWidget(m_btnSetupExtension);

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

    std::string defaultSave = SettingsManager::GetInstance().GetSettings().default_save_dir;
    m_editDir = new QLineEdit(QString::fromStdString(defaultSave), this);
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

    // Row 2: Download Modes (8 Modes including Auto Mode)
    auto *lblMode = new QLabel("Download Mode", this);
    lblMode->setObjectName("fieldLabel");

    auto *modeBox = new QWidget(this);
    auto *modeLayout = new QHBoxLayout(modeBox);
    modeLayout->setContentsMargins(0, 0, 0, 0);
    modeLayout->setSpacing(4);

    m_btnModeNormal = new QPushButton("✓ Normal", this);
    m_btnModeNormal->setObjectName("btnModeActive");
    m_btnModeNetflix = new QPushButton("Netflix", this);
    m_btnModeNetflix->setObjectName("btnModeInactive");
    m_btnModeTitleOnly = new QPushButton("Title Only", this);
    m_btnModeTitleOnly->setObjectName("btnModeInactive");
    m_btnModeImdb = new QPushButton("IMDb", this);
    m_btnModeImdb->setObjectName("btnModeInactive");
    m_btnModeTmdb = new QPushButton("TMDB", this);
    m_btnModeTmdb->setObjectName("btnModeInactive");
    m_btnModeTitleId = new QPushButton("T+ID", this);
    m_btnModeTitleId->setObjectName("btnModeInactive");
    m_btnModeSubMerge = new QPushButton("Sub Merge", this);
    m_btnModeSubMerge->setObjectName("btnModeInactive");
    m_btnModeAuto = new QPushButton("Auto", this);
    m_btnModeAuto->setObjectName("btnModeInactive");

    connect(m_btnModeNormal, &QPushButton::clicked, [this]() { onDownloadModeChanged(0); });
    connect(m_btnModeNetflix, &QPushButton::clicked, [this]() { onDownloadModeChanged(1); });
    connect(m_btnModeTitleOnly, &QPushButton::clicked, [this]() { onDownloadModeChanged(2); });
    connect(m_btnModeImdb, &QPushButton::clicked, [this]() { onDownloadModeChanged(3); });
    connect(m_btnModeTmdb, &QPushButton::clicked, [this]() { onDownloadModeChanged(4); });
    connect(m_btnModeTitleId, &QPushButton::clicked, [this]() { onDownloadModeChanged(5); });
    connect(m_btnModeSubMerge, &QPushButton::clicked, [this]() { onDownloadModeChanged(6); });
    connect(m_btnModeAuto, &QPushButton::clicked, [this]() { onDownloadModeChanged(7); });

    for (auto *b : {m_btnModeNormal, m_btnModeNetflix, m_btnModeTitleOnly, m_btnModeImdb, m_btnModeTmdb, m_btnModeTitleId, m_btnModeSubMerge, m_btnModeAuto}) {
        b->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        b->setMinimumHeight(28);
        b->setCursor(Qt::PointingHandCursor);
        modeLayout->addWidget(b);
    }

    card2Layout->addWidget(lblMode, 2, 0);
    card2Layout->addWidget(modeBox, 2, 1, 1, 3);

    // Row 3: Subtitles Checkbox & Subtitle Track + Format
    auto *lblSubTitle = new QLabel("Subtitles", this);
    lblSubTitle->setObjectName("fieldLabel");
    m_checkEmbedSubs = new QCheckBox("Embed Subtitles into Video (MKV container)", this);
    m_checkEmbedSubs->setObjectName("checkEmbedSubs");
    m_checkEmbedSubs->setChecked(true);

    auto *lblSubFmt = new QLabel("Subtitle Track & Format", this);
    lblSubFmt->setObjectName("fieldLabel");

    auto *subOptBox = new QWidget(this);
    auto *subOptLayout = new QHBoxLayout(subOptBox);
    subOptLayout->setContentsMargins(0, 0, 0, 0);
    subOptLayout->setSpacing(6);

    m_comboSubLang = new QComboBox(this);
    m_comboSubLang->setObjectName("inputCombo");
    m_comboSubLang->addItems({"All Languages", "English (eng)", "Bengali (ben)", "Hindi (hin)", "Spanish (spa)", "French (fra)", "German (deu)", "Japanese (jpn)"});

    m_comboSubFormat = new QComboBox(this);
    m_comboSubFormat->setObjectName("inputCombo");
    m_comboSubFormat->addItems({"SRT (SubRip)", "VTT (WebVTT)"});

    subOptLayout->addWidget(m_comboSubLang, 3);
    subOptLayout->addWidget(m_comboSubFormat, 2);

    card2Layout->addWidget(lblSubTitle, 3, 0);
    card2Layout->addWidget(m_checkEmbedSubs, 3, 1);
    card2Layout->addWidget(lblSubFmt, 3, 2);
    card2Layout->addWidget(subOptBox, 3, 3);

    rootLayout->addWidget(m_card2);

    // ── 5. Action Buttons ─────────────────────────────────────────────────────
    m_actionWidget = new QWidget(this);
    auto *actionLayout = new QHBoxLayout(m_actionWidget);
    actionLayout->setContentsMargins(0, 0, 0, 0);
    actionLayout->setSpacing(10);

    m_btnStart = new QPushButton(" Start Download", this);
    m_btnStart->setIcon(QIcon(":/assets/images/icon_start.png"));
    m_btnStart->setObjectName("btnStartDownload");
    m_btnStart->setCursor(Qt::PointingHandCursor);
    connect(m_btnStart, &QPushButton::clicked, this, &MainWindow::onStartDownloadClicked);
    actionLayout->addWidget(m_btnStart);

    m_btnSubs = new QPushButton(" Download Subtitles", this);
    m_btnSubs->setIcon(QIcon(":/assets/images/icon_subtitles.png"));
    m_btnSubs->setObjectName("btnDownloadSubs");
    m_btnSubs->setCursor(Qt::PointingHandCursor);
    connect(m_btnSubs, &QPushButton::clicked, this, &MainWindow::onDownloadSubtitlesClicked);
    actionLayout->addWidget(m_btnSubs);

    m_btnStop = new QPushButton(" Stop", this);
    m_btnStop->setIcon(QIcon(":/assets/images/icon_stop.png"));
    m_btnStop->setObjectName("btnStop");
    m_btnStop->setCursor(Qt::PointingHandCursor);
    m_btnStop->setEnabled(false);
    connect(m_btnStop, &QPushButton::clicked, this, &MainWindow::onStopClicked);
    actionLayout->addWidget(m_btnStop);

    actionLayout->addStretch();
    rootLayout->addWidget(m_actionWidget);

    // ── 6. Card 3: Live Progress Card ─────────────────────────────────────────
    m_card3 = new QWidget(this);
    m_card3->setObjectName("cardWidget");
    auto *card3Layout = new QVBoxLayout(m_card3);
    card3Layout->setContentsMargins(18, 10, 18, 10);
    card3Layout->setSpacing(5);

    auto *progHeader = new QHBoxLayout();
    auto *progLeft = new QVBoxLayout();
    m_lblProgTitle = new QLabel("Ready to Download", this);
    m_lblProgTitle->setObjectName("cardTitle");
    m_lblProgStatus = new QLabel("Ready — all native C++ dependencies active.", this);
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
    m_card4 = new QWidget(this);
    m_card4->setObjectName("cardWidget");
    auto *card4Layout = new QVBoxLayout(m_card4);
    card4Layout->setContentsMargins(16, 10, 16, 10);
    card4Layout->setSpacing(8);

    // Tab Header
    auto *tabHeader = new QHBoxLayout();
    tabHeader->setSpacing(8);

    m_btnTabQueue = new QPushButton(" Download Queue (0)", this);
    m_btnTabQueue->setObjectName("btnTabActive");
    m_btnTabQueue->setCursor(Qt::PointingHandCursor);
    connect(m_btnTabQueue, &QPushButton::clicked, this, &MainWindow::onTabQueueClicked);
    tabHeader->addWidget(m_btnTabQueue);

    m_btnTabTerminal = new QPushButton(" Terminal", this);
    m_btnTabTerminal->setObjectName("btnTabInactive");
    m_btnTabTerminal->setCursor(Qt::PointingHandCursor);
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

    // Complete Queue Toolbar (Matching Image 2 + Full Feature Set!)
    m_queueToolbarWidget = new QWidget(this);
    auto *queueToolbar = new QHBoxLayout(m_queueToolbarWidget);
    queueToolbar->setContentsMargins(0, 0, 0, 0);
    queueToolbar->setSpacing(6);

    m_btnDownloadAll = new QPushButton(" Downloading...", this);
    m_btnDownloadAll->setIcon(QIcon(":/assets/images/icon_start.png"));
    m_btnDownloadAll->setObjectName("btnDownloadAll");
    m_btnDownloadAll->setCursor(Qt::PointingHandCursor);
    connect(m_btnDownloadAll, &QPushButton::clicked, this, &MainWindow::onDownloadAllClicked);
    queueToolbar->addWidget(m_btnDownloadAll);

    m_btnPauseAll = new QPushButton(" ⏸ Pause All", this);
    m_btnPauseAll->setObjectName("btnToolbar");
    m_btnPauseAll->setCursor(Qt::PointingHandCursor);
    connect(m_btnPauseAll, &QPushButton::clicked, this, &MainWindow::onPauseAllClicked);
    queueToolbar->addWidget(m_btnPauseAll);

    m_btnResumeAll = new QPushButton(" ▶ Resume All", this);
    m_btnResumeAll->setObjectName("btnToolbar");
    m_btnResumeAll->setCursor(Qt::PointingHandCursor);
    connect(m_btnResumeAll, &QPushButton::clicked, this, &MainWindow::onResumeAllClicked);
    queueToolbar->addWidget(m_btnResumeAll);

    m_btnStopAll = new QPushButton(" ⏹ Stop All", this);
    m_btnStopAll->setObjectName("btnToolbarStop");
    m_btnStopAll->setCursor(Qt::PointingHandCursor);
    connect(m_btnStopAll, &QPushButton::clicked, this, &MainWindow::onStopAllClicked);
    queueToolbar->addWidget(m_btnStopAll);

    m_btnClearQueue = new QPushButton("Clear All", this);
    m_btnClearQueue->setObjectName("btnToolbar");
    m_btnClearQueue->setCursor(Qt::PointingHandCursor);
    connect(m_btnClearQueue, &QPushButton::clicked, this, &MainWindow::onClearQueueClicked);
    queueToolbar->addWidget(m_btnClearQueue);

    m_btnFullView = new QPushButton("Full View ↗", this);
    m_btnFullView->setObjectName("btnToolbar");
    m_btnFullView->setCursor(Qt::PointingHandCursor);
    connect(m_btnFullView, &QPushButton::clicked, this, &MainWindow::onFullViewClicked);
    queueToolbar->addWidget(m_btnFullView);

    m_btnImportExcel = new QPushButton("⤓ Import Excel", this);
    m_btnImportExcel->setObjectName("btnToolbar");
    m_btnImportExcel->setCursor(Qt::PointingHandCursor);
    connect(m_btnImportExcel, &QPushButton::clicked, this, &MainWindow::onImportExcelClicked);
    queueToolbar->addWidget(m_btnImportExcel);

    m_btnExportExcel = new QPushButton("↥ Export Excel", this);
    m_btnExportExcel->setObjectName("btnToolbar");
    m_btnExportExcel->setCursor(Qt::PointingHandCursor);
    connect(m_btnExportExcel, &QPushButton::clicked, this, &MainWindow::onExportExcelClicked);
    queueToolbar->addWidget(m_btnExportExcel);

    m_editFilterQueue = new QLineEdit(this);
    m_editFilterQueue->setObjectName("inputField");
    m_editFilterQueue->setPlaceholderText("Filter queue...");
    m_editFilterQueue->setFixedWidth(130);
    connect(m_editFilterQueue, &QLineEdit::textChanged, this, &MainWindow::onFilterQueueChanged);
    queueToolbar->addWidget(m_editFilterQueue);

    queueToolbar->addStretch();

    m_lblQueueStats = new QLabel("Queue: 0 total · 0 active · 0 waiting · 0 done", this);
    m_lblQueueStats->setObjectName("lblQueueStats");
    queueToolbar->addWidget(m_lblQueueStats);

    queuePageLayout->addWidget(m_queueToolbarWidget);

    // Empty Queue Blueprint Widget
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

    auto *lblEmptySub1 = new QLabel("Capture media links using the OmniStream Pro Chrome Extension or paste cURL/links above and click 'Start Download'.", this);
    lblEmptySub1->setObjectName("lblEmptySub");
    lblEmptySub1->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptySub1);

    auto *lblEmptySub2 = new QLabel("When links are added, click 'Downloading...' to batch download like IDM.", this);
    lblEmptySub2->setObjectName("lblEmptySub");
    lblEmptySub2->setAlignment(Qt::AlignCenter);
    placeholderLayout->addWidget(lblEmptySub2);

    queuePageLayout->addWidget(m_emptyQueuePlaceholder);

    // Rich Card-based Queue Scroll Area (Matching Image 2)
    m_queueScrollArea = new QScrollArea(this);
    m_queueScrollArea->setObjectName("queueScrollArea");
    m_queueScrollArea->setWidgetResizable(true);
    m_queueScrollArea->setFrameShape(QFrame::NoFrame);

    m_queueCardsContainer = new QWidget(m_queueScrollArea);
    m_queueCardsLayout = new QVBoxLayout(m_queueCardsContainer);
    m_queueCardsLayout->setContentsMargins(0, 0, 0, 0);
    m_queueCardsLayout->setSpacing(8);
    m_queueCardsLayout->addStretch();

    m_queueScrollArea->setWidget(m_queueCardsContainer);
    m_queueScrollArea->setVisible(false);
    queuePageLayout->addWidget(m_queueScrollArea);

    m_stackedPages->addWidget(m_pageQueue);

    // Page 1: Terminal View
    m_editTerminal = new QPlainTextEdit(this);
    m_editTerminal->setObjectName("editTerminal");
    m_editTerminal->setReadOnly(true);
    m_stackedPages->addWidget(m_editTerminal);

    card4Layout->addWidget(m_stackedPages);
    rootLayout->addWidget(m_card4, 1);

    // ── 8. Footer ─────────────────────────────────────────────────────────────
    auto *footerWidget = new QWidget(this);
    auto *footerLayout = new QHBoxLayout(footerWidget);
    footerLayout->setContentsMargins(4, 2, 4, 0);

    m_lblFooterBridge = new QLabel("⊞ Bridge · Active", this);
    m_lblFooterBridge->setObjectName("lblFooterBridge");
    footerLayout->addWidget(m_lblFooterBridge);

    footerLayout->addStretch();

    m_lblFooterAuthor = new QLabel(
        "OmniStream Pro v2.6.0 · Developed by XMON4U · <a href=\"https://github.com/Xmon4u/OmniStream-Pro-v2\" style=\"color: #58a6ff; text-decoration: none;\">GitHub Repository</a>",
        this);
    m_lblFooterAuthor->setObjectName("lblFooterAuthor");
    m_lblFooterAuthor->setCursor(Qt::PointingHandCursor);
    m_lblFooterAuthor->setOpenExternalLinks(true);
    m_lblFooterAuthor->setTextFormat(Qt::RichText);
    footerLayout->addWidget(m_lblFooterAuthor);

    rootLayout->addWidget(footerWidget);

    onBackendLogMessage("OmniStream Pro v2.6.0 Native C++ Engine loaded.");
    onBackendLogMessage("Database: Native SQLite3 (WAL Mode, High Concurrency).");
    onBackendLogMessage("Bridge Server active on 127.0.0.1:28795.");
}

void MainWindow::applyStyleSheet(int themeIdx) {
    m_currentTheme = themeIdx;
    bool midnight = (themeIdx == 1);
    QString cardBg = midnight ? "#090d14" : "#161b22";
    QString cardBorder = midnight ? "#1e293b" : "#30363d";
    QString inputBg = midnight ? "#020408" : "#090d13";
    QString inputBorder = midnight ? "#1a2234" : "#21262d";
    QString termBg = midnight ? "#000000" : "#05070a";
    QString queueCardBg = midnight ? "#090d14" : "#161b22";

    QString qss = QString(R"(
        QWidget {
            background-color: transparent;
            color: #f0f6fc;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 13px;
        }
        QMainWindow {
            background-color: %1;
            border: 1px solid %2;
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
        #bannerWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e1b4b, stop:0.5 #2e1065, stop:1 #1e1b4b);
            border: 1px solid #4338ca;
            border-radius: 10px;
        }
        #bannerWidget:hover {
            border: 1px solid #818cf8;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #231f5c, stop:0.5 #371477, stop:1 #231f5c);
        }
        #lblBannerText {
            color: #c7d2fe;
            font-size: 12px;
            font-weight: 500;
        }
        #btnBannerSetup {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            border-radius: 6px;
            padding: 4px 12px;
            border: 1px solid #818cf8;
        }
        #btnBannerSetup:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #4f46e5);
            border-color: #a5b4fc;
        }
        #cardWidget {
            background-color: %1;
            border: 1px solid %2;
            border-radius: 12px;
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
        #btnToolbarStop {
            background-color: #7f1d1d;
            border: 1px solid #dc2626;
            border-radius: 6px;
            color: #fca5a5;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
        }
        #btnToolbarStop:hover {
            background-color: #991b1b;
            color: #ffffff;
        }
        #btnModeActive {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            color: #ffffff;
            font-weight: bold;
            border-radius: 6px;
            padding: 4px 6px;
            border: 1px solid #60a5fa;
            font-size: 11px;
            min-height: 26px;
        }
        #btnModeInactive {
            background-color: #090d13;
            color: #8b949e;
            border: 1px solid #21262d;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 11px;
            min-height: 26px;
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
        #lblFooterBridge {
            color: #10b981;
            font-size: 11px;
            font-weight: bold;
        }
        #lblFooterAuthor {
            color: #6e7681;
            font-size: 11px;
        }
        /* Rich Movie Queue Card */
        #queueMovieCard {
            background-color: %6;
            border: 1px solid %2;
            border-radius: 8px;
            padding: 10px 14px;
        }
        #queueMovieCard:hover {
            border: 1px solid #38bdf888;
        }
        #badgeSubMerge {
            background-color: #0f766e;
            color: #2dd4bf;
            font-size: 10px;
            font-weight: bold;
            border-radius: 4px;
            padding: 2px 6px;
        }
        #badgeAuto {
            background-color: #1e3a8a;
            color: #60a5fa;
            font-size: 10px;
            font-weight: bold;
            border-radius: 4px;
            padding: 2px 6px;
        }
        #badgeGeneric {
            background-color: #374151;
            color: #9ca3af;
            font-size: 10px;
            font-weight: bold;
            border-radius: 4px;
            padding: 2px 6px;
        }
        #queueCardTitle {
            font-size: 13px;
            font-weight: bold;
            color: #f0f6fc;
        }
        #queueCardMeta {
            font-size: 11px;
            color: #8b949e;
        }
        #btnCardAction {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb);
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            border-radius: 6px;
            padding: 4px 12px;
            border: 1px solid #38bdf8;
        }
        #btnCardAction:hover {
            background: #2563eb;
        }
        #btnCardCancel {
            background-color: #991b1b;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            border-radius: 6px;
            padding: 4px 12px;
            border: 1px solid #ef4444;
        }
        #btnCardCancel:hover {
            background-color: #b91c1c;
        }
        #btnCardRemove {
            background-color: transparent;
            color: #6e7681;
            font-size: 12px;
            font-weight: bold;
            border: none;
            padding: 2px 6px;
        }
        #btnCardRemove:hover {
            color: #ef4444;
        }
    )").arg(cardBg, cardBorder, inputBg, inputBorder, termBg).arg(queueCardBg);

    setStyleSheet(qss);
}

void MainWindow::onSetupExtensionClicked() {
    onBackendLogMessage("[Extension Setup] Initiating 1-Click Chrome Extension Configuration...");
    m_btnSetupExtension->setEnabled(false);
    m_btnSetupExtension->setText("Setting up...");

    auto res = ExtensionInstaller::InstallExtension([this](const std::string& msg) {
        onBackendLogMessage(QString::fromStdString(msg));
    });

    m_btnSetupExtension->setEnabled(true);

    if (res.success) {
        m_btnSetupExtension->setText("✓ Extension Connected");
        m_btnSetupExtension->setStyleSheet("background: #059669; color: #ffffff; font-weight: bold; border: 1px solid #34d399; border-radius: 6px; padding: 4px 12px; font-size: 11px;");
        onBackendLogMessage("[Extension Setup] Complete. Bridge Token synced.");
        QMessageBox::information(
            this,
            "Extension Setup Completed",
            QString("OmniStream Pro Extension has been configured successfully!\n\n"
                    "Browser: %1\n"
                    "Folder: %2\n\n"
                    "%3\n\n"
                    "Ready to capture video streams from any webpage.")
                .arg(QString::fromStdString(res.browser_path))
                .arg(QString::fromStdString(res.extension_dir))
                .arg(QString::fromStdString(res.message))
        );
    } else {
        m_btnSetupExtension->setText("⚡ Setup Extension (1-Click)");
        QMessageBox::warning(
            this,
            "Extension Setup Notice",
            QString("Extension Setup encountered an issue:\n\n%1\n\n"
                    "Extension Folder: %2\n"
                    "The folder path has been copied to your clipboard.")
                .arg(QString::fromStdString(res.message))
                .arg(QString::fromStdString(res.extension_dir))
        );
    }
}

void MainWindow::onPasteClicked() {
    QClipboard *cb = QApplication::clipboard();
    QString text = cb->text().trimmed();
    if (!text.isEmpty()) {
        m_editUrl->setPlainText(text);
    }
}

void MainWindow::onBrowseClicked() {
    QString dir = QFileDialog::getExistingDirectory(
        this, "Select Save Directory", m_editDir->text()
    );
    if (!dir.isEmpty()) {
        m_editDir->setText(dir);
    }
}

void MainWindow::onStartDownloadClicked() {
    QString raw = m_editUrl->toPlainText().trimmed();
    if (raw.isEmpty()) {
        QMessageBox::warning(this, "Input Required", "Please enter or paste a stream URL or cURL command.");
        return;
    }

    DownloadItem item;
    item.input = raw.toStdString();
    item.title = m_editTitle->text().trimmed().toStdString();
    if (!item.title.empty()) item.user_specified_title = true;

    item.save_dir = m_editDir->text().trimmed().toStdString();
    item.mode = static_cast<DownloadMode>(m_selectedMode);

    QString resRaw = m_comboRes->currentText();
    if (resRaw.contains("1080p")) item.resolution = "1080p";
    else if (resRaw.contains("720p")) item.resolution = "720p";
    else if (resRaw.contains("480p")) item.resolution = "480p";
    else if (resRaw.contains("Audio Only")) item.resolution = "audio_only";
    else item.resolution = "best";

    QString audRaw = m_comboAudio->currentText();
    if (audRaw.contains("Dual Audio")) item.audio_choice = "en_hi";
    else if (audRaw.contains("English Only")) item.audio_choice = "eng";
    else if (audRaw.contains("Hindi Only")) item.audio_choice = "hin";
    else item.audio_choice = "all";

    item.include_subtitles = m_checkEmbedSubs->isChecked();
    item.sub_format = m_comboSubFormat->currentText().contains("VTT") ? "VTT" : "SRT";
    QString subLang = m_comboSubLang->currentText();
    if (subLang.contains("eng")) item.sub_lang = "eng";
    else if (subLang.contains("ben")) item.sub_lang = "ben";
    else if (subLang.contains("hin")) item.sub_lang = "hin";
    else if (subLang.contains("spa")) item.sub_lang = "spa";
    else if (subLang.contains("fra")) item.sub_lang = "fra";
    else if (subLang.contains("deu")) item.sub_lang = "deu";
    else if (subLang.contains("jpn")) item.sub_lang = "jpn";
    else item.sub_lang = "all";

    bool added = QueueManager::GetInstance().AddItem(item, true);
    if (added) {
        m_editUrl->clear();
        m_editTitle->clear();
        m_lblProgTitle->setText(QString::fromStdString(item.title.empty() ? "Starting Download..." : item.title));
        m_lblProgStatus->setText("Enqueued and dispatched to native engine.");
        m_btnStop->setEnabled(true);
    } else {
        QMessageBox::information(this, "Duplicate Item", "This stream or movie is already in the download queue.");
    }
}

void MainWindow::onDownloadSubtitlesClicked() {
    QString raw = m_editUrl->toPlainText().trimmed();
    if (raw.isEmpty()) {
        QMessageBox::warning(this, "Input Required", "Please enter or paste a stream URL or cURL command.");
        return;
    }
    m_editUrl->setPlainText(raw + " --sub-only");
    onStartDownloadClicked();
}

void MainWindow::onStopClicked() {
    QueueManager::GetInstance().CancelAll();
    m_btnStop->setEnabled(false);
    m_lblProgStatus->setText("Stopped by user.");
}

void MainWindow::onTabQueueClicked() {
    m_btnTabQueue->setObjectName("btnTabActive");
    m_btnTabTerminal->setObjectName("btnTabInactive");
    m_btnClearLogs->setVisible(false);
    m_stackedPages->setCurrentIndex(0);
    applyStyleSheet(m_currentTheme);
}

void MainWindow::onTabTerminalClicked() {
    m_btnTabQueue->setObjectName("btnTabInactive");
    m_btnTabTerminal->setObjectName("btnTabActive");
    m_btnClearLogs->setVisible(true);
    m_stackedPages->setCurrentIndex(1);
    applyStyleSheet(m_currentTheme);
}

void MainWindow::onDownloadAllClicked() {
    QueueManager::GetInstance().StartAll();
    m_btnStop->setEnabled(true);
}

void MainWindow::onPauseAllClicked() {
    QueueManager::GetInstance().PauseAll();
}

void MainWindow::onResumeAllClicked() {
    QueueManager::GetInstance().ResumeAll();
    m_btnStop->setEnabled(true);
}

void MainWindow::onStopAllClicked() {
    QueueManager::GetInstance().CancelAll();
    m_btnStop->setEnabled(false);
}

void MainWindow::onClearQueueClicked() {
    if (QueueManager::GetInstance().GetCount() == 0) return;
    auto reply = QMessageBox::question(
        this, "Clear Download Queue",
        "Are you sure you want to remove all items from the download queue?",
        QMessageBox::Yes | QMessageBox::No
    );
    if (reply == QMessageBox::Yes) {
        QueueManager::GetInstance().ClearAll();
    }
}

void MainWindow::onClearLogsClicked() {
    m_editTerminal->clear();
}

void MainWindow::onFullViewClicked() {
    m_isFullView = !m_isFullView;
    m_bannerWidget->setVisible(!m_isFullView);
    m_card1->setVisible(!m_isFullView);
    m_card2->setVisible(!m_isFullView);
    m_actionWidget->setVisible(!m_isFullView);
    m_card3->setVisible(!m_isFullView);

    m_btnFullView->setText(m_isFullView ? "← Back to Dashboard" : "Full View ↗");
}

void MainWindow::onImportExcelClicked() {
    QString path = QFileDialog::getOpenFileName(
        this, "Import Movies from CSV / Spreadsheet", "", "Spreadsheet Files (*.csv *.txt *.xlsx);;CSV Files (*.csv);;Text Files (*.txt);;Excel Files (*.xlsx)"
    );
    if (path.isEmpty()) return;

    if (path.endsWith(".xlsx", Qt::CaseInsensitive)) {
        QMessageBox::information(
            this, "Excel Import Notice",
            "To import this Excel spreadsheet, please save or export it from Excel as a standard CSV file (*.csv).\n\n"
            "Steps: Open file in Excel -> File -> Save As -> 'CSV (Comma delimited) (*.csv)'."
        );
        return;
    }

    std::ifstream in(path.toStdString());
    if (!in.is_open()) {
        QMessageBox::warning(this, "File Error", "Could not open selected spreadsheet file.");
        return;
    }

    auto parseCsvRow = [](const std::string& line) {
        std::vector<std::string> fields;
        std::string cur;
        bool in_quotes = false;
        for (size_t i = 0; i < line.size(); ++i) {
            char c = line[i];
            if (c == '"') {
                if (in_quotes && i + 1 < line.size() && line[i + 1] == '"') {
                    cur += '"';
                    ++i;
                } else {
                    in_quotes = !in_quotes;
                }
            } else if (c == ',' && !in_quotes) {
                fields.push_back(cur);
                cur.clear();
            } else {
                cur += c;
            }
        }
        fields.push_back(cur);
        return fields;
    };

    std::string line;
    int imported = 0;
    while (std::getline(in, line)) {
        if (line.empty() || line.find("SL No") != std::string::npos || line.find("Title,URL") != std::string::npos) continue;
        auto fields = parseCsvRow(line);
        if (fields.empty()) continue;

        std::string title;
        std::string page_url;

        if (fields.size() == 1) {
            page_url = Utils::Trim(fields[0]);
        } else if (fields.size() == 2) {
            title = Utils::Trim(fields[0]);
            page_url = Utils::Trim(fields[1]);
        } else {
            title = Utils::Trim(fields[1]);
            page_url = Utils::Trim(fields[2]);
        }

        // Clean quotes
        auto stripQ = [](std::string& s) {
            if (s.size() >= 2 && s.front() == '"' && s.back() == '"') {
                s = s.substr(1, s.size() - 2);
            }
        };
        stripQ(title);
        stripQ(page_url);

        if (!page_url.empty() && (page_url.find("http://") == 0 || page_url.find("https://") == 0)) {
            DownloadItem item;
            item.title = title.empty() ? "Imported Movie" : title;
            item.input = page_url;
            item.page_url = page_url;
            item.is_auto = true;
            item.needs_resolution = true;
            item.save_dir = SettingsManager::GetInstance().GetSettings().default_save_dir;
            if (QueueManager::GetInstance().AddItem(item, false)) {
                ++imported;
            }
        }
    }

    QMessageBox::information(this, "Import Complete", QString("Successfully imported %1 movies into queue.").arg(imported));
}

void MainWindow::onExportExcelClicked() {
    QString savePath = QFileDialog::getSaveFileName(
        this, "Export Queue to CSV / Excel", QString("OmniStream_Queue_%1.csv").arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss")),
        "CSV Files (*.csv)"
    );
    if (savePath.isEmpty()) return;

    if (QueueManager::GetInstance().ExportToCsv(savePath.toStdString())) {
        QMessageBox::information(this, "Export Succeeded", QString("Queue exported successfully to:\n%1").arg(savePath));
    } else {
        QMessageBox::warning(this, "Export Failed", "Could not write export file.");
    }
}

void MainWindow::onFilterQueueChanged(const QString& text) {
    m_filterText = text.trimmed().toLower();
    rebuildQueueCards();
}

void MainWindow::onOpenSettingsClicked() {
    SettingsDialog dlg(this);
    dlg.exec();
}

void MainWindow::onThemeChanged(int index) {
    applyStyleSheet(index);
}

void MainWindow::onDownloadModeChanged(int modeIdx) {
    m_selectedMode = modeIdx;
    std::vector<std::pair<QPushButton*, QString>> btns = {
        { m_btnModeNormal, "Normal" },
        { m_btnModeNetflix, "Netflix" },
        { m_btnModeTitleOnly, "Title Only" },
        { m_btnModeImdb, "IMDb" },
        { m_btnModeTmdb, "TMDB" },
        { m_btnModeTitleId, "T+ID" },
        { m_btnModeSubMerge, "Sub Merge" },
        { m_btnModeAuto, "Auto" }
    };

    for (size_t i = 0; i < btns.size(); ++i) {
        if (btns[i].first) {
            bool isActive = (static_cast<int>(i) == modeIdx);
            btns[i].first->setObjectName(isActive ? "btnModeActive" : "btnModeInactive");
            btns[i].first->setText(isActive ? ("✓ " + btns[i].second) : btns[i].second);
        }
    }
    applyStyleSheet(m_currentTheme);

    // Sync to backend QueueManager
    DownloadMode mode = static_cast<DownloadMode>(modeIdx);
    if (QueueManager::GetInstance().GetCurrentMode() != mode) {
        QueueManager::GetInstance().SetCurrentMode(mode);
    }
}

void MainWindow::onBackendQueueChanged() {
    rebuildQueueCards();
    updateQueueStats();
}

void MainWindow::onBackendItemUpdated(const DownloadItem& item) {
    updateQueueStats();

        if (item.status == DownloadStatus::Downloading) {
        m_lblProgTitle->setText(QString::fromStdString(item.title));
        m_lblProgStatus->setText(QString::fromStdString(item.progress_text));
        m_lblProgPct->setText(QString::number(static_cast<int>(item.progress_pct)) + "%");
        m_progBar->setValue(static_cast<int>(item.progress_pct));

        QString sizeStr = QString::fromStdString(item.size_str.empty() ? "-- / --" : item.size_str);
        if (!item.eta.empty()) {
            sizeStr += " • ETA: " + QString::fromStdString(item.eta);
        }
        m_lblProgSize->setText("Downloaded: " + sizeStr);
        m_lblProgSpeed->setText(QString::fromStdString(item.speed.empty() ? "0.0 MB/s" : item.speed));

        m_lblStatusBadge->setText(QString::fromUtf8("● Downloading"));
        m_lblStatusBadge->setStyleSheet("background-color: #064e3b; color: #34d399; font-weight: bold; border: 1px solid #059669; border-radius: 12px; padding: 3px 12px;");
    } else if (item.status == DownloadStatus::Completed) {
        m_lblProgTitle->setText(QString::fromStdString(item.title));
        m_lblProgStatus->setText(QString::fromUtf8("Completed • File saved successfully."));
        m_lblProgPct->setText("100%");
        m_progBar->setValue(100);
        m_lblProgSize->setText("Downloaded: " + QString::fromStdString(item.size_str.empty() ? "Complete" : item.size_str));
        m_lblProgSpeed->setText("Complete");
        m_lblStatusBadge->setText(QString::fromUtf8("● Ready"));
        m_lblStatusBadge->setStyleSheet("background-color: #064e3b; color: #34d399; font-weight: bold; border: 1px solid #059669; border-radius: 12px; padding: 3px 12px;");
    } else if (item.status == DownloadStatus::Failed) {
        m_lblProgTitle->setText(QString::fromStdString(item.title));
        m_lblProgStatus->setText(QString::fromStdString("Failed: " + item.error_msg));
        m_lblProgSize->setText("Downloaded: Failed");
        m_lblProgSpeed->setText("0.0 MB/s");
        m_lblStatusBadge->setText(QString::fromUtf8("● Error"));
        m_lblStatusBadge->setStyleSheet("background-color: #7f1d1d; color: #fca5a5; font-weight: bold; border: 1px solid #dc2626; border-radius: 12px; padding: 3px 12px;");
    }

    // Real-time direct Card Updating (Zero UI flicker)
    auto it = m_cardMap.find(item.id);
    if (it != m_cardMap.end()) {
        auto& refs = it->second;
        if (refs.pBar) refs.pBar->setValue(static_cast<int>(item.progress_pct));
        if (refs.lblPct) refs.lblPct->setText(QString::number(static_cast<int>(item.progress_pct)) + "%");
        if (refs.lblProgText) refs.lblProgText->setText(QString::fromStdString(item.progress_text));
        if (refs.lblStatus) {
            refs.lblStatus->setText(QString::fromStdString(DownloadStatusToString(item.status)));
            refs.lblStatus->setStyleSheet(
                item.status == DownloadStatus::Downloading ? "color: #38bdf8; font-weight: bold;" :
                item.status == DownloadStatus::Completed ? "color: #34d399; font-weight: bold;" :
                item.status == DownloadStatus::Failed ? "color: #f87171; font-weight: bold;" :
                "color: #fbbf24; font-weight: 500;"
            );
        }
    }

    // Refresh cards on status transition
    if (item.status == DownloadStatus::Completed || item.status == DownloadStatus::Failed) {
        rebuildQueueCards();
    }
}

void MainWindow::onBackendLogMessage(const QString& msg) {
    m_editTerminal->appendPlainText(msg);
    // Limit terminal buffer to 2000 lines
    if (m_editTerminal->document()->lineCount() > 2000) {
        auto cursor = m_editTerminal->textCursor();
        cursor.movePosition(QTextCursor::Start);
        cursor.movePosition(QTextCursor::Down, QTextCursor::KeepAnchor, 500);
        cursor.removeSelectedText();
    }
}

void MainWindow::rebuildQueueCards() {
    auto items = QueueManager::GetInstance().GetAllItems();

    // Filter items if search text is active
    std::vector<DownloadItem> filtered;
    for (const auto& it : items) {
        if (m_filterText.isEmpty()) {
            filtered.push_back(it);
        } else {
            QString t = QString::fromStdString(it.title).toLower();
            QString u = QString::fromStdString(it.page_url).toLower();
            if (t.contains(m_filterText) || u.contains(m_filterText)) {
                filtered.push_back(it);
            }
        }
    }

    if (filtered.empty()) {
        m_cardMap.clear();
        m_emptyQueuePlaceholder->setVisible(true);
        m_queueScrollArea->setVisible(false);
        return;
    }

    m_emptyQueuePlaceholder->setVisible(false);
    m_queueScrollArea->setVisible(true);
    m_cardMap.clear();

    // Clear existing card widgets
    QLayoutItem *child;
    while ((child = m_queueCardsLayout->takeAt(0)) != nullptr) {
        delete child->widget();
        delete child;
    }

    // Populate Cyber Slate Cards matching Image 2
    for (const auto& item : filtered) {
        auto *card = new QWidget(m_queueCardsContainer);
        card->setObjectName("queueMovieCard");
        auto *cardLayout = new QVBoxLayout(card);
        cardLayout->setContentsMargins(14, 10, 14, 10);
        cardLayout->setSpacing(6);

        // Header: Badge + Title + Action Buttons
        auto *topRow = new QHBoxLayout();
        topRow->setSpacing(8);

        auto *lblBadge = new QLabel(card);
        if (item.mode == DownloadMode::SubMerge) {
            lblBadge->setObjectName("badgeSubMerge");
            lblBadge->setText("SUB MERGE");
        } else if (item.is_auto) {
            lblBadge->setObjectName("badgeAuto");
            lblBadge->setText("AUTO");
        } else {
            lblBadge->setObjectName("badgeGeneric");
            lblBadge->setText(QString::fromStdString(DownloadModeToString(item.mode)).toUpper());
        }
        topRow->addWidget(lblBadge);

        auto *lblTitle = new QLabel(QString::fromStdString(item.title), card);
        lblTitle->setObjectName("queueCardTitle");
        topRow->addWidget(lblTitle);

        topRow->addStretch();

        // Right side: Action button (Download or Cancel) + Remove button
        QString itemId = QString::fromStdString(item.id);
        QPushButton* btnAct = nullptr;
        if (item.status == DownloadStatus::Downloading) {
            auto *btnCancel = new QPushButton("⏹ Cancel", card);
            btnCancel->setObjectName("btnCardCancel");
            btnCancel->setCursor(Qt::PointingHandCursor);
            connect(btnCancel, &QPushButton::clicked, [this, itemId]() { cancelQueueItem(itemId); });
            topRow->addWidget(btnCancel);
            btnAct = btnCancel;
        } else {
            auto *btnStart = new QPushButton("⤓ Download", card);
            btnStart->setObjectName("btnCardAction");
            btnStart->setCursor(Qt::PointingHandCursor);
            connect(btnStart, &QPushButton::clicked, [this, itemId]() { resumeQueueItem(itemId); });
            topRow->addWidget(btnStart);
            btnAct = btnStart;
        }

        auto *btnRemove = new QPushButton("✕", card);
        btnRemove->setObjectName("btnCardRemove");
        btnRemove->setCursor(Qt::PointingHandCursor);
        connect(btnRemove, &QPushButton::clicked, [this, itemId]() { removeQueueItem(itemId); });
        topRow->addWidget(btnRemove);

        cardLayout->addLayout(topRow);

        // Metadata row
        QString meta = QString("Quality: %1 | Audio: %2 | Folder: %3")
            .arg(QString::fromStdString(item.quality.empty() ? item.resolution : item.quality))
            .arg(QString::fromStdString(item.audio_choice))
            .arg(QDir(QString::fromStdString(item.save_dir)).dirName());
        auto *lblMeta = new QLabel(meta, card);
        lblMeta->setObjectName("queueCardMeta");
        cardLayout->addWidget(lblMeta);

        // Status row: Left Status Text + Right Percentage
        auto *statusRow = new QHBoxLayout();
        QString statStr = QString::fromStdString(DownloadStatusToString(item.status));
        auto *lblStat = new QLabel(statStr, card);
        lblStat->setStyleSheet(
            item.status == DownloadStatus::Downloading ? "color: #38bdf8; font-weight: bold;" :
            item.status == DownloadStatus::Completed ? "color: #34d399; font-weight: bold;" :
            item.status == DownloadStatus::Failed ? "color: #f87171; font-weight: bold;" :
            "color: #fbbf24; font-weight: 500;"
        );
        statusRow->addWidget(lblStat);

        statusRow->addStretch();

        auto *lblPct = new QLabel(QString::number(static_cast<int>(item.progress_pct)) + "%", card);
        lblPct->setStyleSheet("color: #94a3b8; font-weight: bold;");
        statusRow->addWidget(lblPct);
        cardLayout->addLayout(statusRow);

        // Progress bar
        auto *pBar = new QProgressBar(card);
        pBar->setObjectName("progBar");
        pBar->setRange(0, 100);
        pBar->setValue(static_cast<int>(item.progress_pct));
        pBar->setTextVisible(false);
        pBar->setFixedHeight(6);
        cardLayout->addWidget(pBar);

        // Speed / Status text footer
        auto *footerRow = new QHBoxLayout();
        auto *lblProgText = new QLabel(QString::fromStdString(item.progress_text), card);
        lblProgText->setStyleSheet("color: #64748b; font-size: 11px;");
        footerRow->addWidget(lblProgText);

        footerRow->addStretch();

        cardLayout->addLayout(footerRow);

        CardWidgetRefs refs;
        refs.card = card;
        refs.lblStatus = lblStat;
        refs.lblPct = lblPct;
        refs.pBar = pBar;
        refs.lblProgText = lblProgText;
        refs.btnAction = btnAct;
        m_cardMap[item.id] = refs;

        // Right-click Context Menu on Card
        card->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(card, &QWidget::customContextMenuRequested, [this, itemId, card](const QPoint& p) {
            QMenu menu(card);
            menu.setStyleSheet(R"(
                QMenu {
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 4px;
                    color: #f0f6fc;
                }
                QMenu::item {
                    padding: 6px 20px 6px 10px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #2563eb;
                    color: #ffffff;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #30363d;
                    margin: 4px 6px;
                }
            )");
            QAction *actStart = menu.addAction("▶ Start / Resume Download");
            QAction *actPause = menu.addAction("⏸ Pause Download");
            QAction *actCancel = menu.addAction("⏹ Cancel Download");
            menu.addSeparator();
            QAction *actPlay = menu.addAction("🎬 Play / Open Video");
            QAction *actOpenDir = menu.addAction("📁 Open Save Folder");
            QAction *actCopyUrl = menu.addAction("🔗 Copy Stream URL");
            menu.addSeparator();
            QAction *actRemove = menu.addAction("🗑 Remove from Queue");

            QAction *chosen = menu.exec(card->mapToGlobal(p));
            if (chosen == actStart) resumeQueueItem(itemId);
            else if (chosen == actPause) pauseQueueItem(itemId);
            else if (chosen == actCancel) cancelQueueItem(itemId);
            else if (chosen == actPlay) playQueueItem(itemId);
            else if (chosen == actOpenDir) openQueueItemLocation(itemId);
            else if (chosen == actCopyUrl) copyQueueItemUrl(itemId);
            else if (chosen == actRemove) removeQueueItem(itemId);
        });

        m_queueCardsLayout->addWidget(card);
    }

    m_queueCardsLayout->addStretch();
}

void MainWindow::updateQueueStats() {
    auto items = QueueManager::GetInstance().GetAllItems();
    int active = 0;
    int waiting = 0;
    int done = 0;

    for (const auto& it : items) {
        if (it.status == DownloadStatus::Downloading) ++active;
        else if (it.status == DownloadStatus::Waiting) ++waiting;
        else if (it.status == DownloadStatus::Completed) ++done;
    }

    m_btnTabQueue->setText(QString(" Download Queue (%1)").arg(items.size()));
    m_lblQueueStats->setText(
        QString("Queue: %1 total · %2 active · %3 waiting · %4 done")
            .arg(items.size())
            .arg(active)
            .arg(waiting)
            .arg(done)
    );
}

void MainWindow::pauseQueueItem(const QString& id) {
    QueueManager::GetInstance().PauseItem(id.toStdString());
}

void MainWindow::resumeQueueItem(const QString& id) {
    QueueManager::GetInstance().ResumeItem(id.toStdString());
    m_btnStop->setEnabled(true);
}

void MainWindow::cancelQueueItem(const QString& id) {
    QueueManager::GetInstance().CancelItem(id.toStdString());
}

void MainWindow::removeQueueItem(const QString& id) {
    QueueManager::GetInstance().RemoveItem(id.toStdString());
}

void MainWindow::playQueueItem(const QString& id) {
    auto item = QueueManager::GetInstance().GetItem(id.toStdString());
    if (!item) return;

    std::filesystem::path filePath;
    if (!item->saved_file.empty() && std::filesystem::exists(item->saved_file)) {
        filePath = item->saved_file;
    } else {
        // Disk fallback: search save_dir for title matching video file
        std::filesystem::path sdir(item->save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item->save_dir);
        std::string sname = MetadataResolver::SanitizeInputTitle(item->title);
        std::vector<std::string> exts = { ".mkv", ".mp4", ".webm", ".ts", ".avi", ".mov" };
        for (const auto& ext : exts) {
            std::filesystem::path cand = sdir / (sname + ext);
            if (std::filesystem::exists(cand)) {
                filePath = cand;
                break;
            }
        }
    }

    if (!filePath.empty() && std::filesystem::exists(filePath)) {
        QDesktopServices::openUrl(QUrl::fromLocalFile(QString::fromStdString(filePath.string())));
    } else {
        QMessageBox::warning(this, "File Not Found", "The downloaded video file could not be found on disk:\n" + QString::fromStdString(filePath.empty() ? item->title : filePath.string()));
    }
}

void MainWindow::openQueueItemLocation(const QString& id) {
    auto item = QueueManager::GetInstance().GetItem(id.toStdString());
    if (!item) return;
    QString dir = QString::fromStdString(item->save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item->save_dir);
    if (!item->saved_file.empty() && std::filesystem::exists(item->saved_file)) {
        QString param = QString("/select,\"%1\"").arg(QDir::toNativeSeparators(QString::fromStdString(item->saved_file)));
        QProcess::startDetached("explorer.exe", QStringList() << param);
    } else {
        QDesktopServices::openUrl(QUrl::fromLocalFile(dir));
    }
}

void MainWindow::copyQueueItemUrl(const QString& id) {
    auto item = QueueManager::GetInstance().GetItem(id.toStdString());
    if (item) {
        QApplication::clipboard()->setText(QString::fromStdString(item->page_url.empty() ? item->input : item->page_url));
    }
}

void MainWindow::showQueueContextMenu(const QPoint& pos) {
    Q_UNUSED(pos);
}

} // namespace OmniStream

