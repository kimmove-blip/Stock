import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Shield } from 'lucide-react';

export default function Privacy() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 헤더 - iOS safe area 대응 */}
      <div className="sticky top-0 bg-white border-b border-gray-200 z-10" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
        <div className="px-4 py-4 flex items-center gap-3 min-h-[60px]">
          <button
            onClick={() => navigate(-1)}
            className="w-12 h-12 flex items-center justify-center hover:bg-gray-100 rounded-xl active:bg-gray-200 transition-colors"
          >
            <ArrowLeft size={24} />
          </button>
          <h1 className="font-bold text-lg">개인정보처리방침</h1>
        </div>
      </div>

      {/* 내용 */}
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="bg-white rounded-xl p-6 shadow-sm">
          {/* 헤더 아이콘 */}
          <div className="flex items-center gap-3 mb-6 pb-4 border-b">
            <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
              <Shield size={24} className="text-purple-600" />
            </div>
            <div>
              <h2 className="font-bold text-gray-800">Kim's AI 주식분석</h2>
              <p className="text-sm text-gray-500">개인정보처리방침</p>
            </div>
          </div>

          <div className="prose prose-sm max-w-none text-gray-700 space-y-6">
            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">1. 개인정보의 수집 및 이용 목적</h3>
              <p className="text-sm leading-relaxed">
                Kim's AI 주식분석(이하 "서비스")은 다음의 목적을 위해 개인정보를 수집 및 이용합니다.
              </p>
              <ul className="list-disc pl-5 text-sm space-y-1 mt-2">
                <li>회원 가입 및 관리: 회원제 서비스 이용에 따른 본인확인, 개인식별</li>
                <li>서비스 제공: AI 기반 주식 분석, 포트폴리오 관리, 관심종목 저장</li>
                <li>알림 서비스: 텔레그램 알림, 이메일 뉴스레터 발송</li>
              </ul>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">2. 수집하는 개인정보 항목</h3>
              <ul className="list-disc pl-5 text-sm space-y-1">
                <li><strong>필수항목:</strong> 이메일 주소, 이름 (Google 계정 연동 시)</li>
                <li><strong>선택항목:</strong> 텔레그램 Chat ID (알림 서비스 이용 시)</li>
                <li><strong>자동수집:</strong> 서비스 이용기록, 접속 로그, 접속 IP</li>
              </ul>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">3. 개인정보의 보유 및 이용기간</h3>
              <p className="text-sm leading-relaxed">
                회원 탈퇴 시까지 보유하며, 탈퇴 요청 시 지체 없이 파기합니다.
                단, 관계 법령에 따라 보존이 필요한 경우 해당 기간 동안 보관합니다.
              </p>
              <ul className="list-disc pl-5 text-sm space-y-1 mt-2">
                <li>서비스 이용기록: 3개월 (통신비밀보호법)</li>
                <li>접속 로그: 3개월 (통신비밀보호법)</li>
              </ul>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">4. 개인정보의 제3자 제공</h3>
              <p className="text-sm leading-relaxed">
                서비스는 이용자의 개인정보를 원칙적으로 제3자에게 제공하지 않습니다.
                다만, 다음의 경우에는 예외로 합니다.
              </p>
              <ul className="list-disc pl-5 text-sm space-y-1 mt-2">
                <li>이용자가 사전에 동의한 경우</li>
                <li>법령의 규정에 의거하거나 수사 목적으로 관계기관의 요청이 있는 경우</li>
              </ul>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">5. 개인정보의 파기</h3>
              <p className="text-sm leading-relaxed">
                개인정보의 수집 및 이용 목적이 달성된 후에는 해당 정보를 지체 없이 파기합니다.
                전자적 파일 형태의 정보는 기술적 방법을 사용하여 복구할 수 없도록 영구 삭제하며,
                그 외의 기록물은 파쇄하거나 소각합니다.
              </p>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">6. 이용자의 권리</h3>
              <p className="text-sm leading-relaxed">
                이용자는 언제든지 다음의 권리를 행사할 수 있습니다.
              </p>
              <ul className="list-disc pl-5 text-sm space-y-1 mt-2">
                <li>개인정보 열람 요청</li>
                <li>개인정보 정정 요청</li>
                <li>개인정보 삭제 요청</li>
                <li>개인정보 처리정지 요청</li>
              </ul>
              <p className="text-sm leading-relaxed mt-2">
                위 권리 행사는 서비스 내 설정 메뉴 또는 문의하기를 통해 가능합니다.
              </p>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">7. 개인정보 보호책임자</h3>
              <p className="text-sm leading-relaxed">
                서비스는 개인정보 처리에 관한 업무를 총괄하여 책임지고,
                개인정보 처리와 관련한 이용자의 불만처리 및 피해구제를 위해
                아래와 같이 개인정보 보호책임자를 지정하고 있습니다.
              </p>
              <div className="bg-gray-50 rounded-lg p-3 mt-2 text-sm">
                <p><strong>개인정보 보호책임자:</strong> 김형철</p>
                <p><strong>문의:</strong> 앱 내 문의하기 기능 이용</p>
              </div>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">8. 개인정보처리방침의 변경</h3>
              <p className="text-sm leading-relaxed">
                이 개인정보처리방침은 시행일로부터 적용되며, 법령 및 방침에 따른 변경 내용의
                추가, 삭제 및 정정이 있는 경우에는 변경사항의 시행 7일 전부터 공지사항을 통하여
                고지할 것입니다.
              </p>
            </section>

            <section>
              <h3 className="text-base font-bold text-gray-800 mb-2">9. 면책 조항</h3>
              <p className="text-sm leading-relaxed">
                본 서비스에서 제공하는 모든 정보(AI 분석, 추천 종목, 기술적 지표 등)는
                투자 참고용 정보이며, 투자 권유가 아닙니다.
                투자에 대한 최종 결정은 이용자 본인의 판단에 따라 이루어져야 하며,
                투자 결과에 대한 책임은 이용자 본인에게 있습니다.
              </p>
            </section>

            <div className="pt-4 border-t text-center text-sm text-gray-500">
              <p>시행일: 2024년 1월 1일</p>
              <p className="mt-1">최종 수정일: 2025년 1월 14일</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
