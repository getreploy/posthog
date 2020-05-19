describe('Sidebar', () => {
    it('Invite Team loads modal', () => {
        cy.get('[data-attr=menu-item-invite-team]').click()

        cy.get('[data-attr=invite-team-modal]').should('be.visible')
    })
})
